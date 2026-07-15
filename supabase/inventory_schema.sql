create table if not exists public.inventory_movements (
    id bigint generated always as identity primary key,
    movement_uid text,
    inventory_scope text,
    movement_type text not null check (movement_type in ('entrada', 'salida')),
    id_registro text,
    codigo text not null,
    descripcion text not null,
    catalogo text,
    marca text,
    lote text,
    cantidad numeric not null default 0,
    unidad text,
    caducidad text,
    ubicacion text,
    categoria text,
    fecha date not null,
    responsable text not null,
    temperatura text,
    observaciones text,
    verificado_por text,
    is_voided boolean not null default false,
    voided_at timestamptz,
    voided_by text,
    void_reason text,
    captured_at timestamptz not null default timezone('utc', now())
);

alter table public.inventory_movements
    add column if not exists movement_uid text;

alter table public.inventory_movements
    add column if not exists inventory_scope text;

alter table public.inventory_movements
    add column if not exists is_voided boolean not null default false;

alter table public.inventory_movements
    add column if not exists voided_at timestamptz;

alter table public.inventory_movements
    add column if not exists voided_by text;

alter table public.inventory_movements
    add column if not exists void_reason text;

update public.inventory_movements
set inventory_scope = 'recuperacion'
where inventory_scope is null or btrim(inventory_scope) = '';

update public.inventory_movements
set movement_uid = md5(random()::text || clock_timestamp()::text || coalesce(codigo, '') || coalesce(fecha::text, ''))
where movement_uid is null or btrim(movement_uid) = '';

alter table public.inventory_movements
    alter column movement_uid set not null;

alter table public.inventory_movements
    alter column inventory_scope set default 'recuperacion';

alter table public.inventory_movements
    alter column inventory_scope set not null;

alter table public.inventory_movements
    drop constraint if exists inventory_movements_inventory_scope_check;

alter table public.inventory_movements
    add constraint inventory_movements_inventory_scope_check
    check (inventory_scope in ('general', 'recuperacion', 'avimex', 'federal', 'lit', 'frontera'));

do $$
begin
    if not exists (
        select 1
        from pg_constraint
        where conname = 'inventory_movements_movement_uid_key'
    ) then
        alter table public.inventory_movements
            add constraint inventory_movements_movement_uid_key unique (movement_uid);
    end if;
end $$;

create index if not exists inventory_movements_scope_idx
    on public.inventory_movements (inventory_scope);

create index if not exists inventory_movements_codigo_idx
    on public.inventory_movements (codigo);

create index if not exists inventory_movements_fecha_idx
    on public.inventory_movements (fecha);

create index if not exists inventory_movements_type_idx
    on public.inventory_movements (movement_type);

create index if not exists inventory_movements_scope_codigo_idx
    on public.inventory_movements (inventory_scope, codigo);

create index if not exists inventory_movements_active_scope_idx
    on public.inventory_movements (inventory_scope, is_voided);


create table if not exists public.inventory_seed_entries (
    id bigint generated always as identity primary key,
    inventory_scope text not null
        check (inventory_scope in ('general', 'recuperacion', 'avimex', 'federal')),
    codigo_local text,
    codigo text not null,
    descripcion text not null,
    catalogo text,
    marca text,
    lote text,
    cantidad numeric not null default 0,
    unidad text,
    caducidad text,
    ubicacion text,
    categoria text,
    source_label text,
    loaded_at timestamptz not null default timezone('utc', now())
);

alter table public.inventory_seed_entries
    drop constraint if exists inventory_seed_entries_inventory_scope_check;

alter table public.inventory_seed_entries
    add constraint inventory_seed_entries_inventory_scope_check
    check (inventory_scope in ('general', 'recuperacion', 'avimex', 'federal', 'lit', 'frontera'));

create index if not exists inventory_seed_entries_scope_idx
    on public.inventory_seed_entries (inventory_scope);

create index if not exists inventory_seed_entries_scope_codigo_idx
    on public.inventory_seed_entries (inventory_scope, codigo);
