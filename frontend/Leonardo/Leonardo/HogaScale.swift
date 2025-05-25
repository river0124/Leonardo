// HogaScale.swift

import Foundation

func getHogaUnit(for price: Int) -> Int {
    switch price {
    case ..<2000: return 1
    case ..<5000: return 5
    case ..<20000: return 10
    case ..<50000: return 50
    case ..<200000: return 100
    case ..<500000: return 500
    default: return 1000
    }
}

func adjustToHoga(price: Int, method: String = "floor") -> Int {
    let unit = getHogaUnit(for: price)
    switch method {
    case "floor":
        return price - (price % unit)
    case "ceil":
        return price % unit == 0 ? price : price + (unit - price % unit)
    case "round":
        return Int((Double(price) / Double(unit)).rounded()) * unit
    default:
        return price // fallback
    }
}
