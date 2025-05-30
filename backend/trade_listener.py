from loguru import logger
from utils import KoreaInvestEnv, KoreaInvestAPI

class TradeListener:
    def __init__(self, cfg, trade_manager, api):

        self.websockets_url = cfg['paper_websocket_url'] if cfg['is_paper_trading'] else cfg['websocket_url']
        self.is_paper = cfg['is_paper_trading']
        self.trade_manager = trade_manager

    async def handle_ws_message(self, message: dict):
        """
        실시간 체결 통보 메시지를 받아 trade_manager에 전달.
        """
        try:
            if self.trade_manager:
                await self.trade_manager.handle_execution(message)
            else:
                logger.warning("⚠️ TradeManager가 초기화되지 않았습니다.")
        except Exception as e:
            logger.error(f"❌ 체결 처리 중 오류: {e}")