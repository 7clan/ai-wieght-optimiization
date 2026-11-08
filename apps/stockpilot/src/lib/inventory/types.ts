export interface InventoryItem {
  id: string
  name: string
  category: string
  sku?: string
  quantity: number
  minQuantity: number
  updatedAt: string
}

export interface InventoryInput {
  name: string
  category: string
  sku?: string
  quantity: number
  minQuantity: number
}

export type StockStatus = 'in stock' | 'low stock' | 'out of stock'

export function stockStatus(
  quantity: number,
  minQuantity: number
): StockStatus {
  if (quantity === 0) return 'out of stock'
  if (quantity <= minQuantity) return 'low stock'
  return 'in stock'
}

