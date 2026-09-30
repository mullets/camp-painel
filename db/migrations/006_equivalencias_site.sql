-- Nome do termo "Fundos" no site -> código da tabela de autoridade
CREATE TABLE fundo_termo_site (
  nome_site    TEXT PRIMARY KEY,
  fundo_codigo TEXT,                                -- NULL = ainda sem decisão (sem FK: pode existir antes do fundo)
  observacao   TEXT
);
INSERT INTO fundo_termo_site (nome_site, fundo_codigo, observacao) VALUES
 ('Arnaldo Antonio Martino','F001',NULL),('Segnini Barretto Arquitetos S/C','F002',NULL),('Burle Marx','F003',NULL),
 ('Carlos Barjas Millan','F004',NULL),('CENPLA','F005',NULL),('Chu Ming Silveira','F006',NULL),('David Libeskind','F007',NULL),
 ('Eduardo de Almeida','F008',NULL),('Euclides Oliveira','F009',NULL),('Francisco Segnini Jr.','F010',NULL),('Hans Broos','F011',NULL),
 ('João Baptista Alves Xavier','F013',NULL),('Joaquim Barretto','F014',NULL),('José Augusto Bellucci','F015',NULL),
 ('José Carlos Bellucci','F016',NULL),('José Gugliotta','F017',NULL),('José Olympio','F018',NULL),('Lauro da Costa Lima','F019',NULL),
 ('Luiz César Barillari','F020',NULL),('Marcos Acayaba','F021',NULL),('Marklen Siag Landa','F022',NULL),
 ('Oswaldo Corrêa Gonçalves','F023',NULL),('Paulo Archias Mendes da Rocha','F024',NULL),('Ruth Verde Zein','F025',NULL),
 ('Sami Bussab','F026',NULL),('Sidnei Magalhães','F028',NULL),('Sylvio Barros Sawaya','F029',NULL),('Fernando e Ana Karazawa','F030',NULL),
 ('João Valente / Sandra Valente',NULL,'no site é um fundo só; na tabela são F012 e F027 — decidir'),
 ('Carlos Henrique Heck',NULL,'sem código na tabela — reservar F031?'),
 ('Major Botkowski',NULL,'sem código na tabela — reservar?');
