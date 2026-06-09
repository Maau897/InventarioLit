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
    captured_at timestamptz not null default timezone('utc', now())
);

alter table public.inventory_movements
    add column if not exists movement_uid text;

alter table public.inventory_movements
    add column if not exists inventory_scope text;

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

do $$
begin
    if not exists (
        select 1
        from pg_constraint
        where conname = 'inventory_movements_inventory_scope_check'
    ) then
        alter table public.inventory_movements
            add constraint inventory_movements_inventory_scope_check
            check (inventory_scope in ('recuperacion', 'avimex', 'federal'));
    end if;
end $$;

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


create table if not exists public.inventory_seed_entries (
    id bigint generated always as identity primary key,
    inventory_scope text not null
        check (inventory_scope in ('recuperacion', 'avimex', 'federal')),
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

create index if not exists inventory_seed_entries_scope_idx
    on public.inventory_seed_entries (inventory_scope);

create index if not exists inventory_seed_entries_scope_codigo_idx
    on public.inventory_seed_entries (inventory_scope, codigo);
