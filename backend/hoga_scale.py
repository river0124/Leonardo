# hoga_scale.py

def get_hoga_unit(price: int) -> int:
    """주어진 가격에 따른 호가 단위를 반환"""
    if price < 2000:
        return 1
    elif price < 5000:
        return 5
    elif price < 20000:
        return 10
    elif price < 50000:
        return 50
    elif price < 200000:
        return 100
    elif price < 500000:
        return 500
    else:
        return 1000

def adjust_price_to_hoga(price: int, method: str = 'floor') -> int:
    """
    가격을 호가 단위 기준으로 조정
    method: 'floor' (내림), 'round' (반올림), 'ceil' (올림)
    """
    unit = get_hoga_unit(price)
    if method == 'floor':
        return price - (price % unit)
    elif method == 'round':
        return int(round(price / unit) * unit)
    elif method == 'ceil':
        return price + (unit - price % unit) if price % unit != 0 else price
    else:
        raise ValueError("method는 'floor', 'round', 'ceil' 중 하나여야 합니다.")