"""
Trading Engine for Dota 2 Arbitrage Bot
Implements trigger logic and automated betting on Polymarket
"""

import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone, timedelta
from motor.motor_asyncio import AsyncIOMotorDatabase

from gsi_server import GameState, GSIServer
from polymarket_client import PolymarketClient

logger = logging.getLogger(__name__)


@dataclass
class TradingConfig:
    """Configuration for trading triggers"""
    gold_advantage_threshold: int = 2000  # Minimum gold advantage
    kills_threshold: int = 3  # Minimum kills in teamfight (30 sec window)
    min_game_time: int = 300  # 5 minutes in seconds
    bet_amount: float = 5.0  # USDC
    cooldown_seconds: int = 60  # Minimum time between bets
    teamfight_window: int = 30  # Seconds to count recent kills


@dataclass
class TriggerEvent:
    """Represents a detected trigger event"""
    trigger_type: str  # "gold_swing", "teamfight", "roshan"
    team: str  # "radiant" or "dire"
    gold_advantage: int
    recent_kills: int
    game_time: int
    timestamp: datetime
    confidence: float = 1.0


class TradingEngine:
    """
    Main trading engine that processes game state and executes trades
    
    Trigger conditions (ALL must be met):
    1. Gold advantage >= threshold (default 2000)
    2. Recent kills >= threshold (default 3 in last 30 seconds)  
    3. Game time >= minimum (default 5 minutes)
    """
    
    def __init__(
        self,
        polymarket_client: Optional[PolymarketClient],
        db: AsyncIOMotorDatabase,
        config: TradingConfig
    ):
        self.polymarket_client = polymarket_client
        self.db = db
        self.config = config
        
        # GSI handler for tracking kills
        self.gsi_handler = GSIServer()
        
        # State tracking
        self.last_bet_time: Optional[datetime] = None
        self.current_market: Optional[Dict[str, Any]] = None
        self.is_active = False
        
        # Previous state for delta detection
        self.previous_gold_advantage: int = 0
        self.bet_count = 0
        
        logger.info(f"TradingEngine initialized with config: {config}")
    
    def set_market(self, market: Dict[str, Any]):
        """Set the current market for betting"""
        self.current_market = market
        logger.info(f"Market set: {market.get('question', 'Unknown')}")
    
    def start(self):
        """Start the trading engine"""
        self.is_active = True
        logger.info("Trading engine started")
    
    def stop(self):
        """Stop the trading engine"""
        self.is_active = False
        logger.info("Trading engine stopped")
    
    async def process_game_state(self, game_state: GameState) -> Optional[TriggerEvent]:
        """
        Process incoming game state and check for trigger conditions
        Returns TriggerEvent if a bet should be placed, None otherwise
        """
        if not self.is_active:
            return None
        
        # Update GSI handler with new state
        self.gsi_handler.process_data(self._game_state_to_dict(game_state))
        
        # Check if game is in progress
        if not game_state.is_in_game:
            return None
        
        # Check minimum game time
        if game_state.game_time < self.config.min_game_time:
            logger.debug(f"Game time {game_state.game_time}s < minimum {self.config.min_game_time}s")
            return None
        
        # Check cooldown
        if self.last_bet_time:
            elapsed = (datetime.now(timezone.utc) - self.last_bet_time).total_seconds()
            if elapsed < self.config.cooldown_seconds:
                logger.debug(f"Cooldown active: {elapsed:.0f}s / {self.config.cooldown_seconds}s")
                return None
        
        # Detect trigger
        trigger = self._detect_trigger(game_state)
        
        if trigger:
            logger.info(f"TRIGGER DETECTED: {trigger.trigger_type} - {trigger.team}")
            logger.info(f"  Gold advantage: {trigger.gold_advantage}")
            logger.info(f"  Recent kills: {trigger.recent_kills}")
            logger.info(f"  Game time: {trigger.game_time}s ({trigger.game_time/60:.1f}min)")
            
            # Execute the trade
            await self._execute_trade(trigger)
            
            return trigger
        
        # Update previous state
        self.previous_gold_advantage = game_state.gold_advantage
        
        return None
    
    def _detect_trigger(self, game_state: GameState) -> Optional[TriggerEvent]:
        """
        Check all trigger conditions
        ALL conditions must be met:
        1. Gold advantage >= threshold
        2. Recent kills >= threshold
        3. Game time >= minimum (already checked)
        """
        gold_advantage = game_state.gold_advantage
        abs_gold_advantage = abs(gold_advantage)
        
        # Determine leading team
        if gold_advantage > 0:
            leading_team = "radiant"
        elif gold_advantage < 0:
            leading_team = "dire"
        else:
            return None
        
        # Check condition 1: Gold advantage
        if abs_gold_advantage < self.config.gold_advantage_threshold:
            logger.debug(f"Gold advantage {abs_gold_advantage} < threshold {self.config.gold_advantage_threshold}")
            return None
        
        # Check condition 2: Recent kills by leading team
        recent_kills = self.gsi_handler.get_recent_kills(
            leading_team, 
            self.config.teamfight_window
        )
        
        if recent_kills < self.config.kills_threshold:
            logger.debug(f"Recent kills {recent_kills} < threshold {self.config.kills_threshold}")
            return None
        
        # All conditions met!
        trigger_type = "teamfight_gold_swing"
        
        # Check if Roshan was involved
        roshan_killer = self.gsi_handler.get_roshan_killer()
        if roshan_killer == leading_team:
            trigger_type = "roshan_kill"
        
        return TriggerEvent(
            trigger_type=trigger_type,
            team=leading_team,
            gold_advantage=abs_gold_advantage,
            recent_kills=recent_kills,
            game_time=game_state.game_time,
            timestamp=datetime.now(timezone.utc)
        )
    
    async def _execute_trade(self, trigger: TriggerEvent):
        """Execute a trade on Polymarket based on the trigger"""
        
        # Log the trade attempt
        trade_log = {
            "id": f"trade_{datetime.now(timezone.utc).timestamp()}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "match_id": self.gsi_handler.current_state.match_id if self.gsi_handler.current_state else "unknown",
            "trigger_type": trigger.trigger_type,
            "team": trigger.team,
            "gold_advantage": trigger.gold_advantage,
            "recent_kills": trigger.recent_kills,
            "game_time": trigger.game_time,
            "bet_amount": self.config.bet_amount,
            "status": "pending"
        }
        
        if not self.current_market:
            logger.warning("No market selected - cannot place bet")
            trade_log["status"] = "no_market"
            trade_log["error_message"] = "No market selected"
            await self._save_trade_log(trade_log)
            return
        
        if not self.polymarket_client:
            logger.warning("Polymarket client not initialized - cannot place bet")
            trade_log["status"] = "no_client"
            trade_log["error_message"] = "Polymarket client not initialized"
            await self._save_trade_log(trade_log)
            return
        
        # Determine which token to buy
        # If trigger.team is "radiant", we assume the market's "Yes" is for the team
        # In reality, you'd need to match the team to the market's specific outcome
        if trigger.team == "radiant":
            token_id = self.current_market.get("yes_token_id")
            side = "BUY"
        else:
            token_id = self.current_market.get("no_token_id")
            side = "BUY"
        
        if not token_id:
            logger.error("No token ID found for the selected market")
            trade_log["status"] = "no_token"
            trade_log["error_message"] = "No token ID found"
            await self._save_trade_log(trade_log)
            return
        
        trade_log["token_id"] = token_id
        
        try:
            # Place the order
            logger.info(f"Placing {side} order for {self.config.bet_amount} USDC on token {token_id[:16]}...")
            
            result = await self.polymarket_client.place_market_order(
                token_id=token_id,
                side=side,
                amount=self.config.bet_amount,
                price_limit=0.95  # Max price to pay (95 cents)
            )
            
            if result.get("success"):
                trade_log["status"] = "success"
                trade_log["order_id"] = result.get("order_id")
                self.last_bet_time = datetime.now(timezone.utc)
                self.bet_count += 1
                logger.info(f"Trade executed successfully! Order ID: {result.get('order_id')}")
            else:
                trade_log["status"] = "failed"
                trade_log["error_message"] = result.get("error", "Unknown error")
                logger.error(f"Trade failed: {result.get('error')}")
                
        except Exception as e:
            trade_log["status"] = "error"
            trade_log["error_message"] = str(e)
            logger.error(f"Trade execution error: {e}")
        
        await self._save_trade_log(trade_log)
    
    async def _save_trade_log(self, trade_log: Dict[str, Any]):
        """Save trade log to database"""
        try:
            await self.db.trade_logs.insert_one(trade_log)
            logger.info(f"Trade log saved: {trade_log['id']} - {trade_log['status']}")
        except Exception as e:
            logger.error(f"Failed to save trade log: {e}")
    
    def _game_state_to_dict(self, game_state: GameState) -> Dict[str, Any]:
        """Convert GameState to dict format expected by GSI handler"""
        return {
            "map": {
                "matchid": game_state.match_id,
                "clock_time": game_state.game_time,
                "game_state": game_state.game_state,
                "radiant_score": game_state.radiant_score,
                "dire_score": game_state.dire_score,
                "roshan_state": game_state.roshan_state,
                "roshan_state_end_seconds": game_state.roshan_state_end_seconds
            },
            "team2": {},  # Radiant players - filled by GSI
            "team3": {}   # Dire players - filled by GSI
        }
    
    def get_status(self) -> Dict[str, Any]:
        """Get current engine status"""
        return {
            "is_active": self.is_active,
            "current_market": self.current_market.get("question") if self.current_market else None,
            "last_bet_time": self.last_bet_time.isoformat() if self.last_bet_time else None,
            "bet_count": self.bet_count,
            "config": {
                "gold_threshold": self.config.gold_advantage_threshold,
                "kills_threshold": self.config.kills_threshold,
                "min_game_time": self.config.min_game_time,
                "bet_amount": self.config.bet_amount
            }
        }


class MockTradingEngine(TradingEngine):
    """
    Mock trading engine for testing without real Polymarket connection
    """
    
    async def _execute_trade(self, trigger: TriggerEvent):
        """Mock trade execution - logs but doesn't actually trade"""
        logger.info("=" * 50)
        logger.info("MOCK TRADE EXECUTION")
        logger.info(f"  Trigger: {trigger.trigger_type}")
        logger.info(f"  Team: {trigger.team}")
        logger.info(f"  Gold Advantage: {trigger.gold_advantage}")
        logger.info(f"  Recent Kills: {trigger.recent_kills}")
        logger.info(f"  Game Time: {trigger.game_time}s")
        logger.info(f"  Bet Amount: {self.config.bet_amount} USDC")
        logger.info("=" * 50)
        
        trade_log = {
            "id": f"mock_trade_{datetime.now(timezone.utc).timestamp()}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "match_id": self.gsi_handler.current_state.match_id if self.gsi_handler.current_state else "test",
            "trigger_type": trigger.trigger_type,
            "team": trigger.team,
            "gold_advantage": trigger.gold_advantage,
            "recent_kills": trigger.recent_kills,
            "game_time": trigger.game_time,
            "bet_amount": self.config.bet_amount,
            "status": "mock_success",
            "order_id": f"mock_order_{self.bet_count}"
        }
        
        self.last_bet_time = datetime.now(timezone.utc)
        self.bet_count += 1
        
        await self._save_trade_log(trade_log)
