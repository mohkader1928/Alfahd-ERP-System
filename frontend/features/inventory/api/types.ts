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
  source_table: string;
  source_id: string;
  moved_at: string;
}

export interface CycleCount {
  id: string;
  company_id: string;
  warehouse_id: string;
  status: "draft" | "counted" | "approved";
  scheduled_date: string;
}

export interface CycleCountLine {
  id: string;
  product_id: string;
  location_id: string;
  system_qty: string;
  counted_qty: string;
  stock_move_id: string | null;
}

export interface CycleCountDetail {
  cycle_count: CycleCount;
  lines: CycleCountLine[];
}

export interface CycleCountLineIn {
  product_id: string;
  location_id: string;
  counted_qty: string;
}
