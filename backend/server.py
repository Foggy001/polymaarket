from fastapi import FastAPI, APIRouter, HTTPException, BackgroundTasks
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timezone
import asyncio
import json

from gsi_server import GSIServer, GameState
from polymarket_client import PolymarketClient
from trading_engine import TradingEngine, TradingConfig

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Create the main app
app = FastAPI(
    title="Dota 2 Arbitrage Bot",
    description="Automated betting bot for Polymarket Dota 2 markets using GSI data",
    version="1.0.0"
)

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global instances
gsi_server: Optional[GSIServer] = None
polymarket_client: Optional[PolymarketClient] = None
trading_engine: Optional[TradingEngine] = None
bot_running = False

# Models
class StatusCheck(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_name: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class StatusCheckCreate(BaseModel):
    client_name: str

class BotConfig(BaseModel):
    gold_advantage_threshold: int = 2000
    kills_threshold: int = 3
    min_game_time: int = 300  # 5 minutes in seconds
    bet_amount: float = 5.0
    market_slug: Optional[str] = None

class TradeLog(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    match_id: str
    trigger_type: str
    team: str
    gold_advantage: int
    recent_kills: int
    game_time: int
    bet_amount: float
    token_id: Optional[str] = None
    order_id: Optional[str] = None
    status: str
    error_message: Optional[str] = None

class MarketInfo(BaseModel):
    slug: str
    title: str
    yes_token_id: str
    no_token_id: str
    volume_24hr: float

# Bot state
class BotState:
    def __init__(self):
        self.is_running = False
        self.current_match_id: Optional[str] = None
        self.current_market: Optional[Dict] = None
        self.last_bet_time: Optional[datetime] = None
        self.config = BotConfig()
        self.game_state: Optional[GameState] = None
        self.recent_kills_radiant: List[int] = []  # timestamps
        self.recent_kills_dire: List[int] = []

bot_state = BotState()

# Routes
@api_router.get("/")
async def root():
    return {"message": "Dota 2 Arbitrage Bot API", "status": "running"}

@api_router.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "bot_running": bot_state.is_running,
        "gsi_connected": gsi_server is not None and gsi_server.is_connected if gsi_server else False,
        "polymarket_connected": polymarket_client is not None,
        "current_match": bot_state.current_match_id,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@api_router.post("/bot/config")
async def update_config(config: BotConfig):
    """Update bot configuration"""
    bot_state.config = config
    if trading_engine:
        trading_engine.config = TradingConfig(
            gold_advantage_threshold=config.gold_advantage_threshold,
            kills_threshold=config.kills_threshold,
            min_game_time=config.min_game_time,
            bet_amount=config.bet_amount
        )
    logger.info(f"Bot config updated: {config.model_dump()}")
    return {"status": "success", "config": config.model_dump()}

@api_router.get("/bot/config")
async def get_config():
    """Get current bot configuration"""
    return bot_state.config.model_dump()

@api_router.post("/bot/start")
async def start_bot(background_tasks: BackgroundTasks):
    """Start the trading bot"""
    global bot_state
    
    if bot_state.is_running:
        return {"status": "already_running"}
    
    bot_state.is_running = True
    logger.info("Bot started - waiting for GSI data")
    
    return {
        "status": "started",
        "message": "Bot started. Connect Dota 2 GSI to receive game data.",
        "gsi_endpoint": "http://localhost:3001"
    }

@api_router.post("/bot/stop")
async def stop_bot():
    """Stop the trading bot"""
    global bot_state
    
    bot_state.is_running = False
    logger.info("Bot stopped")
    
    return {"status": "stopped"}

@api_router.get("/bot/status")
async def get_bot_status():
    """Get current bot status and game state"""
    game_data = None
    if bot_state.game_state:
        gs = bot_state.game_state
        game_data = {
            "match_id": gs.match_id,
            "game_time": gs.game_time,
            "radiant_score": gs.radiant_score,
            "dire_score": gs.dire_score,
            "radiant_net_worth": gs.radiant_net_worth,
            "dire_net_worth": gs.dire_net_worth,
            "gold_advantage": gs.radiant_net_worth - gs.dire_net_worth if gs.radiant_net_worth and gs.dire_net_worth else 0,
            "roshan_state": gs.roshan_state
        }
    
    return {
        "is_running": bot_state.is_running,
        "current_match_id": bot_state.current_match_id,
        "current_market": bot_state.current_market,
        "last_bet_time": bot_state.last_bet_time.isoformat() if bot_state.last_bet_time else None,
        "config": bot_state.config.model_dump(),
        "game_state": game_data
    }

@api_router.get("/markets/dota2")
async def get_dota2_markets():
    """Get available Dota 2 markets from Polymarket"""
    if not polymarket_client:
        raise HTTPException(status_code=503, detail="Polymarket client not initialized")
    
    try:
        markets = await polymarket_client.fetch_dota2_markets()
        return {"markets": markets}
    except Exception as e:
        logger.error(f"Error fetching markets: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/markets/select/{market_slug}")
async def select_market(market_slug: str):
    """Select a market for betting"""
    if not polymarket_client:
        raise HTTPException(status_code=503, detail="Polymarket client not initialized")
    
    try:
        market = await polymarket_client.fetch_market_by_slug(market_slug)
        if market:
            bot_state.current_market = market
            bot_state.config.market_slug = market_slug
            logger.info(f"Selected market: {market_slug}")
            return {"status": "success", "market": market}
        else:
            raise HTTPException(status_code=404, detail="Market not found")
    except Exception as e:
        logger.error(f"Error selecting market: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/trades")
async def get_trades(limit: int = 50):
    """Get recent trade logs"""
    trades = await db.trade_logs.find({}, {"_id": 0}).sort("timestamp", -1).to_list(limit)
    for trade in trades:
        if isinstance(trade.get('timestamp'), str):
            trade['timestamp'] = datetime.fromisoformat(trade['timestamp'])
    return {"trades": trades}

@api_router.get("/balance")
async def get_balance():
    """Get Polymarket account balance"""
    if not polymarket_client:
        raise HTTPException(status_code=503, detail="Polymarket client not initialized")
    
    try:
        balance = await polymarket_client.get_balance()
        return balance
    except Exception as e:
        logger.error(f"Error getting balance: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/test/trigger")
async def test_trigger(team: str = "radiant", trigger_type: str = "gold_swing"):
    """Manually trigger a test bet (for testing purposes)"""
    if not bot_state.is_running:
        raise HTTPException(status_code=400, detail="Bot is not running")
    
    if not bot_state.current_market:
        raise HTTPException(status_code=400, detail="No market selected")
    
    logger.info(f"Test trigger: {trigger_type} for team {team}")
    
    # Create a test trade log
    trade_log = TradeLog(
        match_id="test_match",
        trigger_type=trigger_type,
        team=team,
        gold_advantage=3000,
        recent_kills=4,
        game_time=600,
        bet_amount=bot_state.config.bet_amount,
        status="test"
    )
    
    doc = trade_log.model_dump()
    doc['timestamp'] = doc['timestamp'].isoformat()
    await db.trade_logs.insert_one(doc)
    
    return {"status": "test_triggered", "trade_log": trade_log.model_dump()}

# GSI endpoint for receiving game data
@api_router.post("/gsi")
async def receive_gsi_data(data: Dict[str, Any]):
    """Receive GSI data from Dota 2 client"""
    global bot_state
    
    try:
        # Parse game state
        game_state = parse_gsi_data(data)
        bot_state.game_state = game_state
        
        if game_state.match_id:
            bot_state.current_match_id = game_state.match_id
        
        # Check triggers if bot is running
        if bot_state.is_running and trading_engine:
            await trading_engine.process_game_state(game_state)
        
        return {"status": "received"}
    except Exception as e:
        logger.error(f"Error processing GSI data: {e}")
        return {"status": "error", "message": str(e)}

def parse_gsi_data(data: Dict[str, Any]) -> GameState:
    """Parse raw GSI data into GameState object"""
    map_data = data.get("map", {})
    player_data = data.get("player", {})
    
    # Calculate team net worth from player data
    radiant_net_worth = 0
    dire_net_worth = 0
    
    if "team2" in data:  # Spectator mode - all players visible
        for player_id, player in data.get("team2", {}).items():
            radiant_net_worth += player.get("net_worth", 0)
        for player_id, player in data.get("team3", {}).items():
            dire_net_worth += player.get("net_worth", 0)
    
    return GameState(
        match_id=map_data.get("matchid", ""),
        game_time=map_data.get("clock_time", 0),
        game_state=map_data.get("game_state", ""),
        radiant_score=map_data.get("radiant_score", 0),
        dire_score=map_data.get("dire_score", 0),
        radiant_net_worth=radiant_net_worth,
        dire_net_worth=dire_net_worth,
        roshan_state=map_data.get("roshan_state", "alive"),
        roshan_state_end_seconds=map_data.get("roshan_state_end_seconds", 0)
    )

# Status endpoints (keeping original functionality)
@api_router.post("/status", response_model=StatusCheck)
async def create_status_check(input: StatusCheckCreate):
    status_dict = input.model_dump()
    status_obj = StatusCheck(**status_dict)
    doc = status_obj.model_dump()
    doc['timestamp'] = doc['timestamp'].isoformat()
    await db.status_checks.insert_one(doc)
    return status_obj

@api_router.get("/status", response_model=List[StatusCheck])
async def get_status_checks():
    status_checks = await db.status_checks.find({}, {"_id": 0}).to_list(1000)
    for check in status_checks:
        if isinstance(check['timestamp'], str):
            check['timestamp'] = datetime.fromisoformat(check['timestamp'])
    return status_checks

# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    """Initialize components on startup"""
    global polymarket_client, trading_engine, gsi_server
    
    logger.info("Starting Dota 2 Arbitrage Bot...")
    
    # Initialize Polymarket client
    private_key = os.environ.get('POLYMARKET_PRIVATE_KEY')
    signature_type = int(os.environ.get('SIGNATURE_TYPE', '1'))  # Default to POLY_PROXY
    
    if private_key:
        try:
            polymarket_client = PolymarketClient(
                private_key=private_key,
                signature_type=signature_type
            )
            await polymarket_client.initialize()
            logger.info("Polymarket client initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Polymarket client: {e}")
    else:
        logger.warning("POLYMARKET_PRIVATE_KEY not set - trading disabled")
    
    # Initialize trading engine
    trading_engine = TradingEngine(
        polymarket_client=polymarket_client,
        db=db,
        config=TradingConfig(
            gold_advantage_threshold=bot_state.config.gold_advantage_threshold,
            kills_threshold=bot_state.config.kills_threshold,
            min_game_time=bot_state.config.min_game_time,
            bet_amount=bot_state.config.bet_amount
        )
    )
    
    logger.info("Dota 2 Arbitrage Bot ready")
    logger.info("GSI endpoint: POST /api/gsi")
    logger.info("Configure Dota 2 GSI to send data to this endpoint")

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    global bot_state
    bot_state.is_running = False
    client.close()
    logger.info("Bot shutdown complete")
