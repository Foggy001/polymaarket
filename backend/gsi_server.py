"""
Dota 2 Game State Integration (GSI) Server
Receives and parses live game data from Dota 2 client
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

@dataclass
class GameState:
    """Represents the current state of a Dota 2 match"""
    match_id: str = ""
    game_time: int = 0  # seconds
    game_state: str = ""  # DOTA_GAMERULES_STATE_*
    
    # Team scores
    radiant_score: int = 0
    dire_score: int = 0
    
    # Team net worth (gold)
    radiant_net_worth: int = 0
    dire_net_worth: int = 0
    
    # Roshan state
    roshan_state: str = "alive"  # alive, respawn_base, respawn_variable
    roshan_state_end_seconds: int = 0
    
    # Recent events tracking
    last_radiant_score: int = 0
    last_dire_score: int = 0
    last_update_time: datetime = field(default_factory=datetime.now)
    
    @property
    def gold_advantage(self) -> int:
        """Returns Radiant's gold advantage (negative means Dire leads)"""
        return self.radiant_net_worth - self.dire_net_worth
    
    @property
    def radiant_kills_delta(self) -> int:
        """Returns kills gained by Radiant since last update"""
        return self.radiant_score - self.last_radiant_score
    
    @property
    def dire_kills_delta(self) -> int:
        """Returns kills gained by Dire since last update"""
        return self.dire_score - self.last_dire_score
    
    @property
    def is_in_game(self) -> bool:
        """Check if game is actively being played"""
        return self.game_state in [
            "DOTA_GAMERULES_STATE_GAME_IN_PROGRESS",
            "DOTA_GAMERULES_STATE_PRE_GAME"
        ]
    
    @property
    def game_time_minutes(self) -> float:
        """Game time in minutes"""
        return self.game_time / 60.0


class GSIServer:
    """
    Handler for Dota 2 Game State Integration data
    Tracks game state and detects significant events
    """
    
    def __init__(self):
        self.is_connected = False
        self.current_state: Optional[GameState] = None
        self.previous_state: Optional[GameState] = None
        
        # Kill tracking for teamfight detection
        self.radiant_kill_times: List[int] = []  # game_time of kills
        self.dire_kill_times: List[int] = []
        
        # Roshan tracking
        self.last_roshan_killer: Optional[str] = None  # "radiant" or "dire"
        self.roshan_was_alive = True
        
    def process_data(self, data: Dict[str, Any]) -> GameState:
        """Process raw GSI data and return updated GameState"""
        
        # Store previous state
        if self.current_state:
            self.previous_state = GameState(
                match_id=self.current_state.match_id,
                game_time=self.current_state.game_time,
                game_state=self.current_state.game_state,
                radiant_score=self.current_state.radiant_score,
                dire_score=self.current_state.dire_score,
                radiant_net_worth=self.current_state.radiant_net_worth,
                dire_net_worth=self.current_state.dire_net_worth,
                roshan_state=self.current_state.roshan_state,
                roshan_state_end_seconds=self.current_state.roshan_state_end_seconds,
                last_radiant_score=self.current_state.last_radiant_score,
                last_dire_score=self.current_state.last_dire_score
            )
        
        # Parse new state
        new_state = self._parse_gsi_data(data)
        
        # Update kill times for teamfight detection
        if self.previous_state:
            new_state.last_radiant_score = self.previous_state.radiant_score
            new_state.last_dire_score = self.previous_state.dire_score
            
            # Track kill times
            radiant_new_kills = new_state.radiant_score - self.previous_state.radiant_score
            dire_new_kills = new_state.dire_score - self.previous_state.dire_score
            
            for _ in range(radiant_new_kills):
                self.radiant_kill_times.append(new_state.game_time)
            for _ in range(dire_new_kills):
                self.dire_kill_times.append(new_state.game_time)
            
            # Clean old kill times (older than 30 seconds)
            cutoff_time = new_state.game_time - 30
            self.radiant_kill_times = [t for t in self.radiant_kill_times if t > cutoff_time]
            self.dire_kill_times = [t for t in self.dire_kill_times if t > cutoff_time]
        
        # Detect Roshan kill
        if self.roshan_was_alive and new_state.roshan_state != "alive":
            # Roshan was just killed
            # Determine which team killed based on gold swing
            if self.previous_state:
                gold_diff = new_state.gold_advantage - self.previous_state.gold_advantage
                if gold_diff > 0:
                    self.last_roshan_killer = "radiant"
                else:
                    self.last_roshan_killer = "dire"
                logger.info(f"Roshan killed by {self.last_roshan_killer}! Gold swing: {gold_diff}")
        
        self.roshan_was_alive = new_state.roshan_state == "alive"
        self.current_state = new_state
        self.is_connected = True
        
        return new_state
    
    def _parse_gsi_data(self, data: Dict[str, Any]) -> GameState:
        """Parse raw GSI JSON data into GameState object"""
        
        map_data = data.get("map", {})
        
        # Calculate team net worth
        radiant_net_worth = 0
        dire_net_worth = 0
        
        # In spectator mode, teams are under "team2" (radiant) and "team3" (dire)
        for player_id, player in data.get("team2", {}).items():
            if isinstance(player, dict):
                radiant_net_worth += player.get("net_worth", 0)
        
        for player_id, player in data.get("team3", {}).items():
            if isinstance(player, dict):
                dire_net_worth += player.get("net_worth", 0)
        
        # Alternative: check player data directly
        if radiant_net_worth == 0 and dire_net_worth == 0:
            player_data = data.get("player", {})
            if isinstance(player_data, dict):
                team = player_data.get("team_name", "")
                net_worth = player_data.get("net_worth", 0)
                if team == "radiant":
                    radiant_net_worth = net_worth
                elif team == "dire":
                    dire_net_worth = net_worth
        
        return GameState(
            match_id=str(map_data.get("matchid", "")),
            game_time=map_data.get("clock_time", 0),
            game_state=map_data.get("game_state", ""),
            radiant_score=map_data.get("radiant_score", 0),
            dire_score=map_data.get("dire_score", 0),
            radiant_net_worth=radiant_net_worth,
            dire_net_worth=dire_net_worth,
            roshan_state=map_data.get("roshan_state", "alive"),
            roshan_state_end_seconds=map_data.get("roshan_state_end_seconds", 0)
        )
    
    def get_recent_kills(self, team: str, window_seconds: int = 30) -> int:
        """Get number of kills by a team in the last N seconds"""
        if not self.current_state:
            return 0
        
        cutoff_time = self.current_state.game_time - window_seconds
        
        if team == "radiant":
            return len([t for t in self.radiant_kill_times if t > cutoff_time])
        elif team == "dire":
            return len([t for t in self.dire_kill_times if t > cutoff_time])
        
        return 0
    
    def detect_teamfight(self, min_kills: int = 3, window_seconds: int = 30) -> Optional[str]:
        """
        Detect if a significant teamfight occurred
        Returns winning team or None
        """
        radiant_kills = self.get_recent_kills("radiant", window_seconds)
        dire_kills = self.get_recent_kills("dire", window_seconds)
        
        if radiant_kills >= min_kills and radiant_kills > dire_kills:
            return "radiant"
        elif dire_kills >= min_kills and dire_kills > radiant_kills:
            return "dire"
        
        return None
    
    def get_roshan_killer(self) -> Optional[str]:
        """Returns the team that last killed Roshan, or None"""
        return self.last_roshan_killer


# GSI Configuration file content for Dota 2
GSI_CONFIG = """
"dota2-gsi"
{
    "uri"           "http://localhost:8001/api/gsi"
    "timeout"       "5.0"
    "buffer"        "0.1"
    "throttle"      "0.1"
    "heartbeat"     "30.0"
    "data"
    {
        "provider"      "1"
        "map"           "1"
        "player"        "1"
        "hero"          "1"
        "abilities"     "1"
        "items"         "1"
        "events"        "1"
        "buildings"     "1"
        "league"        "1"
        "draft"         "1"
        "wearables"     "0"
    }
    "auth"
    {
        "token"         "dota2arbitragebot"
    }
}
"""

def get_gsi_config_instructions() -> str:
    """Returns instructions for setting up GSI in Dota 2"""
    return f"""
=== Dota 2 GSI Setup Instructions ===

1. Navigate to your Dota 2 game folder:
   - Windows: C:\\Program Files (x86)\\Steam\\steamapps\\common\\dota 2 beta\\game\\dota\\cfg\\gamestate_integration\\
   - Linux: ~/.steam/steam/steamapps/common/dota 2 beta/game/dota/cfg/gamestate_integration/
   - Mac: ~/Library/Application Support/Steam/steamapps/common/dota 2 beta/game/dota/cfg/gamestate_integration/

2. Create the 'gamestate_integration' folder if it doesn't exist

3. Create a file named 'gamestate_integration_bot.cfg' with this content:

{GSI_CONFIG}

4. Launch Dota 2 with the launch option: -gamestateintegration

5. Join a match as spectator to start receiving data

=== End Instructions ===
"""
