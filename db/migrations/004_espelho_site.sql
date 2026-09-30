-- Espelho do que existe no site (WordPress/Tainacan), preenchido pelo sincronizador.
-- Nunca é editado à mão: reflete o site; o painel compara com suas próprias tabelas.
CREATE TABLE wp_colecao (
  id          INTEGER PRIMARY KEY,           -- id no Tainacan
  nome        TEXT, slug TEXT, url TEXT,
  total_itens INTEGER,
  json        TEXT,
  visto_em    TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE wp_taxonomia (
  id INTEGER PRIMARY KEY, nome TEXT, slug TEXT, json TEXT, visto_em TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE wp_termo (
  id INTEGER PRIMARY KEY, taxonomia_id INTEGER, nome TEXT, slug TEXT, pai_id INTEGER,
  codigo_detectado TEXT, json TEXT, visto_em TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE wp_item (
  id            INTEGER PRIMARY KEY,           -- id do item no Tainacan (post id)
  colecao_id    INTEGER,
  status        TEXT,                          -- publish | draft | private | ...
  titulo        TEXT, slug TEXT, url TEXT,
  documento_url TEXT, thumb_url TEXT,
  codigo_detectado TEXT,                       -- F0xx-P000x-AAAA-S0x-DNNNNN, ou parte dele
  fundo_detectado TEXT,
  projeto_detectado TEXT,
  metadados     TEXT,                          -- JSON {nome: valor_texto}
  modificado_em TEXT,
  json          TEXT,
  visto_em      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX wp_item_codigo ON wp_item(codigo_detectado);
CREATE INDEX wp_item_fundo ON wp_item(fundo_detectado);
CREATE TABLE wp_pagina (
  id INTEGER PRIMARY KEY, titulo TEXT, slug TEXT, url TEXT, status TEXT, pai_id INTEGER,
  codigo_detectado TEXT, json TEXT, visto_em TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE sincronizacao (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  iniciada_em TEXT NOT NULL DEFAULT (datetime('now')), terminada_em TEXT,
  ok INTEGER, colecoes INTEGER, itens INTEGER, termos INTEGER, paginas INTEGER,
  divergencias INTEGER, erro TEXT
);
