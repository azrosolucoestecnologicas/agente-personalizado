-- =====================================================================
--  Base de conhecimento do assistente (Parte 2: RAG)
--
--  Pode rodar de novo sem estragar nada (idempotente):
--  Supabase → SQL Editor → cole este arquivo → Run.
--
--  Permissões (menor privilégio):
--   - chave PUBLICÁVEL (papel anon): só LÊ a coleção 'producao' e chama buscar_hibrido.
--     Não vê a 'teste', não grava, não apaga, não promove.
--   - chave SECRETA (papel service_role): grava, apaga e promove. Fica só no GitHub.
-- =====================================================================

create extension if not exists vector with schema extensions;
create extension if not exists unaccent with schema extensions;

-- Busca por palavras em português, sem diferenciar acentos ("funcao" = "função")
-- e reduzindo à raiz ("guardo" e "guardar" viram "guard").
do $$
begin
  if not exists (select 1 from pg_ts_config where cfgname = 'pt_sem_acento') then
    create text search configuration public.pt_sem_acento (copy = pg_catalog.portuguese);
    alter text search configuration public.pt_sem_acento
      alter mapping for hword, hword_part, word with extensions.unaccent, portuguese_stem;
  end if;
end $$;

-- ---------------------------------------------------------------- tabela
create table if not exists public.trechos (
  id          bigint generated always as identity primary key,
  colecao     text not null check (colecao in ('teste', 'producao')),
  fonte       text not null,                   -- ex.: parte2-rag.md
  secao       text not null,                   -- ex.: 09 Chunking: dividir para achar
  ordem       int  not null,                   -- posição do trecho dentro do documento
  conteudo    text not null,                   -- texto do trecho (começa com o título da seção)
  embedding   extensions.vector(768) not null, -- e5-base: 768 dimensões, normalizado
  modelo      text not null,                   -- modelo que gerou o vetor
  texto_busca tsvector generated always as (to_tsvector('public.pt_sem_acento'::regconfig, conteudo)) stored,
  criado_em   timestamptz not null default now()
);
-- Troca de modelo: a 1ª versão usava o e5-small (384 números); agora é o e5-base (768).
-- Se a coluna ainda tiver outro tamanho, os vetores antigos não servem para o modelo
-- novo: apaga os trechos (o próximo indexar.py regrava) e muda o tamanho da coluna.
-- Com a coluna já em 768, este bloco não faz nada.
do $$
begin
  if (select atttypmod from pg_attribute
      where attrelid = 'public.trechos'::regclass and attname = 'embedding') <> 768 then
    delete from public.trechos;
    alter table public.trechos alter column embedding type extensions.vector(768);
  end if;
end $$;

create index if not exists trechos_colecao_idx on public.trechos (colecao);
create index if not exists trechos_texto_busca_idx on public.trechos using gin (texto_busca);
-- Sem índice HNSW: com centenas de trechos, a busca exata é rápida e sempre certa.

comment on table public.trechos is
  'Trechos dos documentos da pasta documentos/. Coleção teste = em avaliação; producao = o que o assistente no ar consulta.';

-- ------------------------------------------------- busca híbrida com RRF
-- Palavras + sentido, fundidas por RRF: nota = peso / (rrf_k + posição) em cada lista.
-- security invoker: roda com as permissões de quem chama. Com a chave publicável,
-- a RLS só deixa passar linhas 'producao', mesmo que peçam p_colecao => 'teste'.
create or replace function public.buscar_hibrido(
  consulta text,
  consulta_embedding extensions.vector(768),
  quantidade int default 4,
  peso_palavras float default 1.0,
  peso_sentido float default 1.0,
  rrf_k int default 60,
  candidatos int default 20,
  p_colecao text default 'producao'
) returns table (
  id bigint, fonte text, secao text, conteudo text,
  similaridade float, nota_rrf float, pos_palavras int, pos_sentido int
)
language sql stable security invoker
set search_path = public, extensions
as $$
  with
  termos as (  -- termos da pergunta combinados com OU (perguntas naturais, não frases exatas)
    select nullif(replace(plainto_tsquery('public.pt_sem_acento'::regconfig, consulta)::text, '&', '|'), '')::tsquery as q
  ),
  por_palavras as (
    select t.id, row_number() over (order by ts_rank_cd(t.texto_busca, termos.q) desc, t.id) as pos
    from public.trechos t, termos
    where t.colecao = p_colecao and peso_palavras > 0 and termos.q is not null and t.texto_busca @@ termos.q
    order by pos
    limit candidatos
  ),
  por_sentido as (
    select t.id, row_number() over (order by t.embedding <=> consulta_embedding, t.id) as pos
    from public.trechos t
    where t.colecao = p_colecao and peso_sentido > 0
    order by pos
    limit candidatos
  ),
  fundido as (
    select coalesce(p.id, s.id) as id,
           coalesce(peso_palavras / (rrf_k + p.pos), 0) + coalesce(peso_sentido / (rrf_k + s.pos), 0) as nota,
           p.pos as pos_p, s.pos as pos_s
    from por_palavras p full outer join por_sentido s on p.id = s.id
  )
  select t.id, t.fonte, t.secao, t.conteudo,
         1 - (t.embedding <=> consulta_embedding) as similaridade,
         f.nota as nota_rrf, f.pos_p::int as pos_palavras, f.pos_s::int as pos_sentido
  from fundido f
  join public.trechos t on t.id = f.id
  order by f.nota desc, t.id
  limit quantidade;
$$;

-- --------------------------------------------- funções do GitHub Actions
-- Apaga a coleção 'teste' antes de reindexar.
create or replace function public.limpar_teste() returns int
language plpgsql security invoker
set search_path = public, extensions
as $$
declare n int;
begin
  delete from public.trechos where colecao = 'teste';
  get diagnostics n = row_count;
  return n;
end $$;

-- Promoção: 'teste' vira 'producao' de uma vez (a função inteira é uma transação).
create or replace function public.promover_teste() returns int
language plpgsql security invoker
set search_path = public, extensions
as $$
declare n int;
begin
  select count(*) into n from public.trechos where colecao = 'teste';
  if n = 0 then
    raise exception 'Coleção teste vazia: nada a promover';
  end if;
  delete from public.trechos where colecao = 'producao';
  insert into public.trechos (colecao, fonte, secao, ordem, conteudo, embedding, modelo)
    select 'producao', fonte, secao, ordem, conteudo, embedding, modelo
    from public.trechos where colecao = 'teste';
  return n;
end $$;

-- ------------------------------------------------------------ permissões
alter table public.trechos enable row level security;

revoke all on public.trechos from anon, authenticated;
grant select on public.trechos to anon, authenticated;

-- Cria a regra só se ainda não existir (sem "drop": nada é apagado ao rodar de novo).
do $$
begin
  if not exists (select 1 from pg_policies where schemaname = 'public' and tablename = 'trechos'
                 and policyname = 'leitura da producao') then
    create policy "leitura da producao" on public.trechos
      for select to anon, authenticated
      using (colecao = 'producao');
  end if;
end $$;
-- Sem políticas de INSERT/UPDATE/DELETE: a chave publicável não grava nada.

revoke all on function public.limpar_teste() from public, anon, authenticated;
revoke all on function public.promover_teste() from public, anon, authenticated;
grant execute on function public.limpar_teste() to service_role;
grant execute on function public.promover_teste() to service_role;

revoke all on function public.buscar_hibrido(text, extensions.vector, int, float, float, int, int, text) from public;
grant execute on function public.buscar_hibrido(text, extensions.vector, int, float, float, int, int, text)
  to anon, authenticated, service_role;
-- A chave secreta (papel service_role) ignora a RLS: grava, apaga e promove.
