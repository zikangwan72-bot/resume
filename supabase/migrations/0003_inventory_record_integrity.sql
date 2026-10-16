-- One asset can only have one record in a single inventory task.
create unique index if not exists uq_inventory_record_task_asset
  on public.inventory_records (task_id, asset_id);
