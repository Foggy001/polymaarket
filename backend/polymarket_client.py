"""
Polymarket CLOB API Client
Handles authentication, market data fetching, and order placement
Using official py-clob-client SDK
"""

import os
import logging
import httpx
from typing import Dict, Any, Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)

# Polymarket API endpoints
CLOB_HOST = "https://clob.polymarket.com"
GAMMA_HOST = "https://gamma-api.polymarket.com"
POLYGON_CHAIN_ID = 137

# Try to import py-clob-client
try:
    from py_clob_client.client import ClobClient
    from py_clob_client.clob_types import ApiCreds, OrderArgs, OrderType
    from py_clob_client.constants import POLYGON
    HAS_CLOB_CLIENT = True
except ImportError:
    HAS_CLOB_CLIENT = False
    logger.warning("py-clob-client not available, using HTTP-only mode")


class PolymarketClient:
    """
    Client for interacting with Polymarket's CLOB API
    """
    
    def __init__(
        self,
        private_key: str,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        api_passphrase: Optional[str] = None,
        signature_type: int = 0,
        funder_address: Optional[str] = None
    ):
        self.private_key = private_key
        # Ensure private key has 0x prefix
        if not self.private_key.startswith('0x'):
            self.private_key = '0x' + self.private_key
            
        self.signature_type = signature_type
        self.funder_address = funder_address
        
        # L2 API credentials
        self.api_key = api_key
        self.api_secret = api_secret
        self.api_passphrase = api_passphrase
        
        # HTTP client for market data
        self.http_client = httpx.AsyncClient(timeout=30.0)
        
        # CLOB client
        self.clob_client: Optional[ClobClient] = None
        self.address: Optional[str] = None
        
        self.initialized = False
        
    async def initialize(self):
        """Initialize the client"""
        if HAS_CLOB_CLIENT:
            try:
                # For POLY_PROXY (signature_type=1), use the funder address from settings
                logger.info(f"Initializing with funder address: {self.funder_address}")
                
                # Create CLOB client with funder address
                self.clob_client = ClobClient(
                    host=CLOB_HOST,
                    key=self.private_key,
                    chain_id=POLYGON_CHAIN_ID,
                    signature_type=self.signature_type,
                    funder=self.funder_address
                )
                
                # Get address from client
                self.address = self.clob_client.get_address()
                logger.info(f"CLOB Client signer address: {self.address}")
                
                # Derive API credentials
                logger.info("Deriving API credentials...")
                try:
                    # Use derive_api_key with nonce=0 for proper L2 auth
                    creds = self.clob_client.derive_api_key(nonce=0)
                    self.api_key = creds.api_key
                    self.api_secret = creds.api_secret
                    self.api_passphrase = creds.api_passphrase
                    
                    # Set the credentials on the client for L2 auth
                    self.clob_client.set_api_creds(creds)
                    
                    logger.info("API credentials derived and set successfully!")
                    logger.info(f"API Key: {self.api_key[:20]}...")
                except Exception as creds_err:
                    logger.warning(f"Could not derive credentials: {creds_err}")
                    logger.info("Trading may be limited, but market data available")
                
                self.initialized = True
                logger.info("PolymarketClient initialized with CLOB SDK")
                
            except Exception as e:
                logger.error(f"Failed to initialize CLOB client: {e}")
                logger.info("Falling back to HTTP-only mode (market data only)")
                self.initialized = True  # Still allow market data fetching
        else:
            logger.info("Running in HTTP-only mode (no trading capability)")
            self.initialized = True
    
    async def fetch_dota2_markets(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Fetch active Dota 2 prediction markets from Polymarket
        """
        try:
            # Search for all markets and filter for Dota 2
            params = {
                "active": "true",
                "closed": "false",
                "limit": 100,
                "order": "volume24hr",
                "ascending": "false"
            }
            
            response = await self.http_client.get(
                f"{GAMMA_HOST}/markets",
                params=params
            )
            
            if response.status_code != 200:
                logger.error(f"Failed to fetch markets: {response.text}")
                return []
            
            all_markets = response.json()
            
            # Filter for Dota 2 related markets
            dota_keywords = ["dota", "dota2", "dota 2", "ti2025", "international", "esport"]
            dota_markets = []
            
            for market in all_markets:
                question = market.get("question", "").lower()
                description = market.get("description", "").lower()
                tags = [t.get("slug", "").lower() for t in market.get("tags", [])]
                
                is_dota = any(
                    kw in question or kw in description or kw in " ".join(tags)
                    for kw in dota_keywords
                )
                
                if is_dota:
                    dota_markets.append(self._format_market(market))
            
            logger.info(f"Found {len(dota_markets)} Dota 2 / esports markets")
            return dota_markets[:limit]
            
        except Exception as e:
            logger.error(f"Error fetching Dota 2 markets: {e}")
            return []
    
    async def fetch_market_by_slug(self, slug: str) -> Optional[Dict[str, Any]]:
        """Fetch a specific market by its slug"""
        try:
            response = await self.http_client.get(
                f"{GAMMA_HOST}/markets",
                params={"slug": slug}
            )
            
            if response.status_code != 200:
                logger.error(f"Failed to fetch market {slug}: {response.text}")
                return None
            
            markets = response.json()
            if markets and len(markets) > 0:
                return self._format_market(markets[0])
            
            return None
            
        except Exception as e:
            logger.error(f"Error fetching market {slug}: {e}")
            return None
    
    def _format_market(self, market: Dict[str, Any]) -> Dict[str, Any]:
        """Format market data for internal use"""
        clob_token_ids = market.get("clobTokenIds", [])
        
        return {
            "id": market.get("id"),
            "slug": market.get("slug"),
            "question": market.get("question"),
            "description": market.get("description", ""),
            "volume_24hr": float(market.get("volume24hr", 0)),
            "liquidity": float(market.get("liquidity", 0)),
            "yes_token_id": clob_token_ids[0] if len(clob_token_ids) > 0 else None,
            "no_token_id": clob_token_ids[1] if len(clob_token_ids) > 1 else None,
            "tick_size": market.get("minimum_tick_size", "0.01"),
            "neg_risk": market.get("neg_risk", False),
            "active": market.get("active", False),
            "closed": market.get("closed", False)
        }
    
    async def get_orderbook(self, token_id: str) -> Dict[str, Any]:
        """Fetch the order book for a specific token"""
        try:
            if self.clob_client:
                book = self.clob_client.get_order_book(token_id)
                return book
            else:
                response = await self.http_client.get(
                    f"{CLOB_HOST}/book",
                    params={"token_id": token_id}
                )
                
                if response.status_code != 200:
                    logger.error(f"Failed to fetch orderbook: {response.text}")
                    return {"bids": [], "asks": []}
                
                return response.json()
            
        except Exception as e:
            logger.error(f"Error fetching orderbook: {e}")
            return {"bids": [], "asks": []}
    
    async def get_balance(self) -> Dict[str, Any]:
        """Get account balance and allowances"""
        try:
            if self.clob_client and self.api_key:
                from py_clob_client.clob_types import BalanceAllowanceParams, AssetType
                
                # Get COLLATERAL (USDC) balance
                params = BalanceAllowanceParams(
                    asset_type=AssetType.COLLATERAL,
                    signature_type=self.signature_type
                )
                balance = self.clob_client.get_balance_allowance(params)
                return balance
            else:
                return {"balance": "N/A", "allowance": "N/A", "note": "CLOB client not fully initialized"}
            
        except Exception as e:
            logger.error(f"Error getting balance: {e}")
            return {"balance": 0, "allowance": 0, "error": str(e)}
    
    async def place_market_order(
        self,
        token_id: str,
        side: str,  # "BUY" or "SELL"
        amount: float,
        price_limit: float
    ) -> Dict[str, Any]:
        """
        Place a market order (Fill-Or-Kill)
        """
        if not self.clob_client:
            return {
                "success": False,
                "error": "CLOB client not initialized - trading disabled"
            }
        
        try:
            from py_clob_client.clob_types import MarketOrderArgs, OrderType
            from py_clob_client.order_builder.constants import BUY, SELL
            
            side_enum = BUY if side.upper() == "BUY" else SELL
            
            # Create market order with all required args
            order_args = MarketOrderArgs(
                token_id=token_id,
                amount=amount,
                side=side_enum,
                price=price_limit
            )
            
            # Create the order
            signed_order = self.clob_client.create_market_order(order_args)
            
            # Post the order
            result = self.clob_client.post_order(signed_order, OrderType.FOK)
            
            logger.info(f"Market order placed: {result}")
            return {
                "success": True,
                "order_id": result.get("orderID"),
                "status": result.get("status")
            }
            
        except Exception as e:
            logger.error(f"Error placing market order: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def place_limit_order(
        self,
        token_id: str,
        side: str,
        price: float,
        size: float
    ) -> Dict[str, Any]:
        """
        Place a limit order (Good-Til-Cancelled)
        """
        if not self.clob_client:
            return {
                "success": False,
                "error": "CLOB client not initialized - trading disabled"
            }
        
        try:
            from py_clob_client.clob_types import OrderArgs, OrderType
            from py_clob_client.order_builder.constants import BUY, SELL
            
            side_enum = BUY if side.upper() == "BUY" else SELL
            
            order_args = OrderArgs(
                price=price,
                size=size,
                side=side_enum,
                token_id=token_id
            )
            
            result = self.clob_client.create_and_post_order(order_args)
            
            logger.info(f"Limit order placed: {result}")
            return {
                "success": True,
                "order_id": result.get("orderID"),
                "status": result.get("status")
            }
            
        except Exception as e:
            logger.error(f"Error placing limit order: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """Cancel an open order"""
        if not self.clob_client:
            return {"success": False, "error": "CLOB client not initialized"}
        
        try:
            result = self.clob_client.cancel(order_id)
            return {"success": True, "canceled": result.get("canceled", [])}
            
        except Exception as e:
            logger.error(f"Error canceling order: {e}")
            return {"success": False, "error": str(e)}
    
    async def get_open_orders(self) -> List[Dict[str, Any]]:
        """Get all open orders"""
        if not self.clob_client:
            return []
        
        try:
            orders = self.clob_client.get_orders()
            return orders
            
        except Exception as e:
            logger.error(f"Error getting orders: {e}")
            return []
    
    async def close(self):
        """Close the HTTP client"""
        await self.http_client.aclose()
