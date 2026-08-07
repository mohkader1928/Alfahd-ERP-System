export interface NotificationRow {
  id: string;
  type: string;
  title: string;
  body: string;
  entity_type: string | null;
  entity_id: string | null;
  link: string | null;
  is_read: boolean;
  created_at: string;
}
