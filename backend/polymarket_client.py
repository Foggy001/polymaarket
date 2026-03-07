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
    HAS_CLOB_CLIENT = True
except ImportError:
    HAS_CLOB_CLIENT = False
    logger.warning("py-clob-client not available, using HTTP-only mode")


def patch_httpx_proxy(proxy_url: str):
    """
    Patch py-clob-client's httpx client to use proxy.
    This must be called BEFORE any API calls are made.
    """
    try:
        # Import the helpers module directly
        import py_clob_client.http_helpers.helpers as helpers
        
        # Close existing client if any
        if hasattr(helpers, '_http_client') and helpers._http_client:
            try:
                helpers._http_client.close()
            except:
                pass
        
        # Create new client with proxy - using mounts for better control
        transport = httpx.HTTPTransport(proxy=proxy_url)
        new_client = httpx.Client(
            http2=True,
            timeout=60.0,
            mounts={
                "http://": transport,
                "https://": transport,
            }
        )
        
        # Replace the global client
        helpers._http_client = new_client
        logger.info(f"Successfully patched py-clob-client httpx with proxy: {proxy_url[:40]}...")
        return True
        
    except Exception as e:
        logger.error(f"Failed to patch httpx: {e}")
        return False


class PolymarketClient:
    """
    Client for interacting with Polymarket's CLOB API
    """
    
    def __init__(
        self,
        private_key: str,
        funder_address: Optional[str] = None,
        signature_type: int = 1,
        proxy: Optional[str] = None  # format: host:port:user:pass or host:port
    ):
        self.private_key = private_key
        if not self.private_key.startswith('0x'):
            self.private_key = '0x' + self.private_key
            
        self.signature_type = signature_type
        self.funder_address = funder_address
        self.proxy = proxy
        
        # Parse proxy
        self.proxy_url = None
        if proxy:
            self.proxy_url = self._parse_proxy(proxy)
        
        # L2 API credentials
        self.api_key = None
        self.api_secret = None
        self.api_passphrase = None
        
        # HTTP client
        self.http_client = None
        
        # CLOB client
        self.clob_client: Optional[ClobClient] = None
        self.address: Optional[str] = None
        
        self.initialized = False
    
    def _parse_proxy(self, proxy: str) -> str:
        """Parse proxy string to URL format"""
        parts = proxy.split(':')
        if len(parts) == 4:
            host, port, user, password = parts
            return f"http://{user}:{password}@{host}:{port}"
        elif len(parts) == 2:
            host, port = parts
            return f"http://{host}:{port}"
        return None
        
    async def initialize(self):
        """Initialize the client"""
        # IMPORTANT: Patch py-clob-client's httpx BEFORE creating ClobClient
        if self.proxy_url:
            success = patch_httpx_proxy(self.proxy_url)
            if success:
                logger.info(f"Proxy configured for py-clob-client: {self.proxy_url[:40]}...")
            else:
                logger.warning("Failed to configure proxy for py-clob-client")
            
            # Also create async client with proxy for our own requests (Gamma API)
            transport = httpx.AsyncHTTPTransport(proxy=self.proxy_url)
            self.http_client = httpx.AsyncClient(
                timeout=30.0,
                mounts={
                    "http://": transport,
                    "https://": transport,
                }
            )
        else:
            self.http_client = httpx.AsyncClient(timeout=30.0)
        
        if HAS_CLOB_CLIENT:
            try:
                logger.info(f"Initializing with funder: {self.funder_address}")
                logger.info(f"Using proxy: {self.proxy_url[:40] if self.proxy_url else 'None'}...")
                
                self.clob_client = ClobClient(
                    host=CLOB_HOST,
                    key=self.private_key,
                    chain_id=POLYGON_CHAIN_ID,
                    signature_type=self.signature_type,
                    funder=self.funder_address
                )
                
                self.address = self.clob_client.get_address()
                logger.info(f"Signer address: {self.address}")
                
                # Derive API credentials
                logger.info("Deriving API credentials...")
                try:
                    creds = self.clob_client.derive_api_key(nonce=0)
                    self.api_key = creds.api_key
                    self.api_secret = creds.api_secret
                    self.api_passphrase = creds.api_passphrase
                    self.clob_client.set_api_creds(creds)
                    logger.info("API credentials set successfully!")
                except Exception as e:
                    logger.warning(f"Could not derive credentials: {e}")
                
                self.initialized = True
                logger.info("PolymarketClient initialized with proxy support")
                
            except Exception as e:
                logger.error(f"Failed to initialize: {e}")
                self.initialized = True
        else:
            self.initialized = True
    
    async def fetch_market_by_slug(self, slug: str) -> Optional[Dict[str, Any]]:
        """Fetch a specific market by its slug"""
        try:
            response = await self.http_client.get(
                f"{GAMMA_HOST}/markets",
                params={"slug": slug}
            )
            
            if response.status_code != 200:
                return None
            
            markets = response.json()
            if markets and len(markets) > 0:
                return markets[0]
            return None
            
        except Exception as e:
            logger.error(f"Error fetching market {slug}: {e}")
            return None
    
    async def get_balance(self) -> Dict[str, Any]:
        """Get account balance and allowances"""
        try:
            if self.clob_client and self.api_key:
                from py_clob_client.clob_types import BalanceAllowanceParams, AssetType
                params = BalanceAllowanceParams(
                    asset_type=AssetType.COLLATERAL,
                    signature_type=self.signature_type
                )
                balance = self.clob_client.get_balance_allowance(params)
                return balance
            return {"balance": "N/A", "note": "Client not initialized"}
        except Exception as e:
            logger.error(f"Error getting balance: {e}")
            return {"balance": 0, "error": str(e)}
    
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
    
    async def place_market_order(
        self,
        token_id: str,
        side: str,
        amount: float,
        price_limit: float
    ) -> Dict[str, Any]:
        """Place a market order"""
        if not self.clob_client:
            return {"success": False, "error": "Client not initialized"}
        
        try:
            from py_clob_client.clob_types import MarketOrderArgs, OrderType
            from py_clob_client.order_builder.constants import BUY, SELL
            
            side_enum = BUY if side.upper() == "BUY" else SELL
            
            order_args = MarketOrderArgs(
                token_id=token_id,
                amount=amount,
                side=side_enum,
                price=price_limit
            )
            
            signed_order = self.clob_client.create_market_order(order_args)
            result = self.clob_client.post_order(signed_order, OrderType.FOK)
            
            logger.info(f"Order placed: {result}")
            return {
                "success": True,
                "order_id": result.get("orderID"),
                "status": result.get("status")
            }
            
        except Exception as e:
            logger.error(f"Error placing order: {e}")
            return {"success": False, "error": str(e)}
    
    async def place_limit_order(
        self,
        token_id: str,
        side: str,
        price: float,
        size: float
    ) -> Dict[str, Any]:
        """Place a limit order"""
        if not self.clob_client:
            return {"success": False, "error": "Client not initialized"}
        
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
            
            signed_order = self.clob_client.create_order(order_args)
            result = self.clob_client.post_order(signed_order, OrderType.GTC)
            
            return {
                "success": True,
                "order_id": result.get("orderID"),
                "status": result.get("status")
            }
            
        except Exception as e:
            logger.error(f"Error placing limit order: {e}")
            return {"success": False, "error": str(e)}
    
    async def close(self):
        """Close the HTTP client"""
        if self.http_client:
            await self.http_client.aclose()
