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

create table if not exists public.usuarios_app (
    id_usuario bigint generated always as identity primary key,
    email text unique not null,
    password_hash text not null,
    aprobado boolean not null default false,
    es_admin boolean not null default false,
    rol text not null default 'captura',
    fecha_registro timestamptz not null default now()
);

alter table public.usuarios_app
    add column if not exists rol text not null default 'captura';

create index if not exists idx_usuarios_app_email
    on public.usuarios_app (email);

create index if not exists idx_usuarios_app_aprobado
    on public.usuarios_app (aprobado);

create table if not exists public.inventario_auditoria (
    id_evento bigint generated always as identity primary key,
    email text not null,
    accion text not null,
    detalle text,
    created_at timestamptz not null default now()
);

create index if not exists idx_inventario_auditoria_created_at
    on public.inventario_auditoria (created_at desc);

create index if not exists idx_inventario_auditoria_email
    on public.inventario_auditoria (email);

alter table public.usuarios_app enable row level security;

alter table public.inventario_auditoria enable row level security;

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


create table if not exists public.inventory_physical_counts (
    id bigint generated always as identity primary key,
    count_uid text,
    inventory_scope text,
    codigo text not null,
    descripcion text not null,
    catalogo text,
    marca text,
    lote text,
    unidad text,
    ubicacion text,
    categoria text,
    existencia_anterior numeric not null default 0,
    conteo_fisico numeric not null default 0,
    verificacion_fisica numeric not null default 0,
    conteos_empatan boolean not null default false,
    diferencia numeric,
    ajuste_aplicado boolean not null default false,
    movement_uid text,
    fecha_conteo date not null,
    contador text not null,
    verificador text not null,
    observaciones text,
    captured_at timestamptz not null default timezone('utc', now())
);

alter table public.inventory_physical_counts
    add column if not exists count_uid text;

alter table public.inventory_physical_counts
    add column if not exists inventory_scope text;

alter table public.inventory_physical_counts
    add column if not exists codigo text;

alter table public.inventory_physical_counts
    add column if not exists descripcion text;

alter table public.inventory_physical_counts
    add column if not exists catalogo text;

alter table public.inventory_physical_counts
    add column if not exists marca text;

alter table public.inventory_physical_counts
    add column if not exists lote text;

alter table public.inventory_physical_counts
    add column if not exists unidad text;

alter table public.inventory_physical_counts
    add column if not exists ubicacion text;

alter table public.inventory_physical_counts
    add column if not exists categoria text;

alter table public.inventory_physical_counts
    add column if not exists existencia_anterior numeric not null default 0;

alter table public.inventory_physical_counts
    add column if not exists conteo_fisico numeric not null default 0;

alter table public.inventory_physical_counts
    add column if not exists verificacion_fisica numeric not null default 0;

alter table public.inventory_physical_counts
    add column if not exists conteos_empatan boolean not null default false;

alter table public.inventory_physical_counts
    add column if not exists diferencia numeric;

alter table public.inventory_physical_counts
    add column if not exists ajuste_aplicado boolean not null default false;

alter table public.inventory_physical_counts
    add column if not exists movement_uid text;

alter table public.inventory_physical_counts
    add column if not exists fecha_conteo date;

alter table public.inventory_physical_counts
    add column if not exists contador text;

alter table public.inventory_physical_counts
    add column if not exists verificador text;

alter table public.inventory_physical_counts
    add column if not exists observaciones text;

alter table public.inventory_physical_counts
    add column if not exists captured_at timestamptz not null default timezone('utc', now());

update public.inventory_physical_counts
set inventory_scope = 'lit'
where inventory_scope is null or btrim(inventory_scope) = '';

update public.inventory_physical_counts
set count_uid = md5(random()::text || clock_timestamp()::text || coalesce(codigo, '') || coalesce(fecha_conteo::text, ''))
where count_uid is null or btrim(count_uid) = '';

alter table public.inventory_physical_counts
    alter column count_uid set not null;

alter table public.inventory_physical_counts
    alter column inventory_scope set default 'lit';

alter table public.inventory_physical_counts
    alter column inventory_scope set not null;

alter table public.inventory_physical_counts
    drop constraint if exists inventory_physical_counts_inventory_scope_check;

alter table public.inventory_physical_counts
    add constraint inventory_physical_counts_inventory_scope_check
    check (inventory_scope in ('general', 'recuperacion', 'avimex', 'federal', 'lit', 'frontera'));

do $$
begin
    if not exists (
        select 1
        from pg_constraint
        where conname = 'inventory_physical_counts_count_uid_key'
    ) then
        alter table public.inventory_physical_counts
            add constraint inventory_physical_counts_count_uid_key unique (count_uid);
    end if;
end $$;

create index if not exists inventory_physical_counts_scope_idx
    on public.inventory_physical_counts (inventory_scope);

create index if not exists inventory_physical_counts_catalogo_idx
    on public.inventory_physical_counts (catalogo);

create index if not exists inventory_physical_counts_fecha_idx
    on public.inventory_physical_counts (fecha_conteo);

create index if not exists inventory_physical_counts_scope_catalogo_idx
    on public.inventory_physical_counts (inventory_scope, catalogo);

alter table public.inventory_physical_counts enable row level security;
