/** Mirrors backend `shared/api/pagination.py`'s `Page[T]` envelope — the
 * shared shape any server-side-paginated list endpoint returns. */
export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}
