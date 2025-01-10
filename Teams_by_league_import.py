import requests
import json
from datetime import datetime, timedelta, timezone
from functools import lru_cache

API_KEY = '8d6adb05582ab584f36f361197f5a59f1aa2b0d899b10ce3a3717f8bf896e1ea'

# Slovník pro mapování soutěží - přesunut na úroveň modulu pro lepší přístup
COMPETITION_NAMES = {
    12336: "Chance liga",
    12529: "Bundesliga",
    12530: "Serie A",
    12337: "Ligue 1",
    12325: "Premier league",
    12316: "La Liga"
}

SEASON_IDS = {
    "Premier league": 12325,
    "La Liga": 12316,
    "Bundesliga": 12529,
    "Serie A": 12530,
    "Ligue 1": 12337,
    "Chance liga": 12336
}

# Cache pro API volání
@lru_cache(maxsize=32)
def make_api_request(url):
    """
    Cachovaná funkce pro API požadavky
    """
    response = requests.get(url)
    if response.status_code == 200:
        return response.json()
    return None

def get_league_teams_positions():
    """
    Získá pozice týmů pro všechny ligy a vrátí je jako dictionary
    """
    positions = {}
    
    for competition, season_id in SEASON_IDS.items():
        url = f"https://api.football-data-api.com/league-teams?key={API_KEY}&season_id={season_id}&include=stats"
        data = make_api_request(url)
        
        if data and 'data' in data:
            positions[competition] = {
                team['id']: team['table_position']
                for team in data['data']
                if 'id' in team and 'table_position' in team
            }
            
            # Ukládání JSON odpovědi do souboru
            with open(f'league_teams_{season_id}.json', 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
    
    return positions

def get_matches_for_next_days():
    today = datetime.now(timezone.utc).date()
    all_matches = []
    team_positions = get_league_teams_positions()
    
    # Získání zápasů pro příštích 7 dní v jednom API volání
    end_date = today + timedelta(days=7)
    url = f"https://api.football-data-api.com/matches-between?key={API_KEY}&from={today}&to={end_date}"
    
    data = make_api_request(url)
    if data:
        matches = data.get('data', [])
        
        filtered_matches = [
            {
                "id": match.get("id"),
                "homeID": match.get("homeID"),
                "awayID": match.get("awayID"),
                "home_name": match.get("home_name"),
                "away_name": match.get("away_name"),
                "competition": COMPETITION_NAMES.get(match.get('competition_id'), "Unknown"),
                "date": datetime.fromtimestamp(match.get("date_unix"), timezone.utc).strftime('%Y-%m-%d') if match.get("date_unix") else None,
                "home_position": team_positions.get(COMPETITION_NAMES.get(match.get('competition_id')), {}).get(match.get("homeID")),
                "away_position": team_positions.get(COMPETITION_NAMES.get(match.get('competition_id')), {}).get(match.get("awayID"))
            }
            for match in matches
            if match.get('competition_id') in COMPETITION_NAMES
        ]
        
        with open('matches.json', 'w', encoding='utf-8') as json_file:
            json.dump(filtered_matches, json_file, indent=4, ensure_ascii=False)

@lru_cache(maxsize=128)
def find_match_by_teams(team1_id, team2_id):
    """
    Cachovaná funkce pro vyhledávání zápasů
    """
    with open('matches.json', 'r', encoding='utf-8') as file:
        matches = json.load(file)
    
    return next((match for match in matches 
                if (match['homeID'] == team1_id and match['awayID'] == team2_id) or
                   (match['homeID'] == team2_id and match['awayID'] == team1_id)), None)

@lru_cache(maxsize=128)
def get_team_stats(team_id):
    """
    Cachovaná funkce pro statistiky týmů
    """
    url = f"https://api.football-data-api.com/lastx?key={API_KEY}&team_id={team_id}"
    data = make_api_request(url)
    
    if data:
        with open(f'team_stats_{team_id}.json', 'w', encoding='utf-8') as json_file:
            json.dump(data, json_file, indent=4, ensure_ascii=False)
        return data
    return None

def calculate_win_probability(home_stats, away_stats, match):
    """
    Vypočítá pravděpodobnost výhry domácího týmu s přidanou vahou pro pozici v tabulce
    """
    # Základní parametry (původní váhy)
    home_goals_weight = 0.15
    away_goals_weight = 0.15
    home_clean_sheets_weight = 0.1
    away_clean_sheets_weight = 0.1
    home_form_weight = 0.1
    away_form_weight = 0.1
    
    # Nová váha pro pozici v tabulce (největší váha)
    table_position_weight = 0.3
    
    # Výpočet skóre z gólů
    home_goals_score = home_stats.get('goals_scored_per_match', 0) * home_goals_weight
    away_goals_score = away_stats.get('goals_scored_per_match', 0) * away_goals_weight
    
    # Výpočet skóre z čistých kont
    home_clean_sheets_score = home_stats.get('clean_sheets_ratio', 0) * home_clean_sheets_weight
    away_clean_sheets_score = away_stats.get('clean_sheets_ratio', 0) * away_clean_sheets_weight
    
    # Výpočet skóre z formy
    home_form_score = home_stats.get('form_ratio', 0) * home_form_weight
    away_form_score = away_stats.get('form_ratio', 0) * away_form_weight
    
    # Výpočet skóre z pozice v tabulce
    home_position = match.get('home_position', 20)  # defaultně poslední místo
    away_position = match.get('away_position', 20)  # defaultně poslední místo
    max_position = 20  # předpokládáme ligu s 20 týmy
    
    # Převedení pozice na skóre (čím nižší pozice, tím vyšší skóre)
    home_position_score = ((max_position - home_position) / max_position) * table_position_weight
    away_position_score = ((max_position - away_position) / max_position) * table_position_weight
    
    # Celkové skóre pro oba týmy
    home_total_score = (
        home_goals_score + 
        home_clean_sheets_score + 
        home_form_score + 
        home_position_score
    )
    
    away_total_score = (
        away_goals_score + 
        away_clean_sheets_score + 
        away_form_score + 
        away_position_score
    )
    
    # Přidání výhody domácího prostředí (10%)
    home_advantage = 0.1
    home_total_score *= (1 + home_advantage)
    
    # Výpočet pravděpodobnosti
    total_score = home_total_score + away_total_score
    if total_score == 0:
        return 0.5  # Pokud nemáme data, vracíme 50%
    
    home_win_probability = home_total_score / total_score
    
    return home_win_probability

def calculate_match_probabilities(team1_id, team2_id):
    """
    Optimalizovaný výpočet pravděpodobností
    """
    match = find_match_by_teams(team1_id, team2_id)
    if not match:
        return None
        
    team1_stats = get_team_stats(team1_id)
    team2_stats = get_team_stats(team2_id)
    
    if not team1_stats or not team2_stats:
        return None
    
    home_win_prob = calculate_win_probability(team1_stats, team2_stats, match)
    draw_prob = 0.24
    away_win_prob = 1 - home_win_prob - draw_prob
    
    if away_win_prob < 0:
        away_win_prob = 0.05
        total = home_win_prob + draw_prob
        ratio = 0.95 / total
        home_win_prob *= ratio
        draw_prob *= ratio
    
    return {
        'team1': {'name': match['home_name'], 'win_probability': round(home_win_prob * 100)},
        'team2': {'name': match['away_name'], 'win_probability': round(away_win_prob * 100)},
        'draw_probability': round(draw_prob * 100)
    }

def main():
    try:
        # Get matches for next days
        get_matches_for_next_days()
        
        team1_id = int(input("Zadejte ID prvního týmu: "))
        team2_id = int(input("Zadejte ID druhého týmu: "))
        
        match = find_match_by_teams(team1_id, team2_id)
        if not match:
            print("Zápas mezi zadanými týmy nebyl nalezen.")
            return
            
        print(f"\nNalezen zápas: {match['home_name']} vs {match['away_name']}")
        
        # Výpočet pravděpodobností
        probabilities = calculate_match_probabilities(team1_id, team2_id)
        if probabilities:
            print("\nPravděpodobnosti výsledku:")
            print(f"Výhra {probabilities['team1']['name']}: {probabilities['team1']['win_probability']}%")
            print(f"Remíza: {probabilities['draw_probability']}%")
            print(f"Výhra {probabilities['team2']['name']}: {probabilities['team2']['win_probability']}%")
            
    except ValueError:
        print("Chyba: Zadejte prosím platná číselná ID týmů.")

if __name__ == "__main__":
    main()