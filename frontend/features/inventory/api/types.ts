export interface Warehouse {
  id: string;
  company_id: string;
  branch_id: string;
  name: string;
  is_default: boolean;
}

export interface Location {
  id: string;
  name: string;
  is_virtual: boolean;
}

export interface WarehouseCreateResult {
  warehouse: Warehouse;
  default_location: Location;
}

export interface StockQuant {
  product_id: string;
  location_id: string;
  qty_on_hand: string;
  moving_avg_cost: string;
}

export interface StockMove {
  id: string;
  product_id: string;
  source_location_id: string | null;
  dest_location_id: string | null;
  qty: string;
  unit_cost: string;
  move_type: string;
}
