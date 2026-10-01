-- Normaliza a infraestrutura física da CAMP.
-- Preserva o IP legado do Contex como Contex 1 e remove a chave ambígua antiga.
INSERT OR IGNORE INTO configuracao (chave, valor, descricao, sensivel)
SELECT 'estacao.contex1.ip', valor, 'IP da Estação Contex 1', 0
  FROM configuracao WHERE chave='estacao.contex.ip';

INSERT OR IGNORE INTO configuracao (chave, valor, descricao, sensivel)
SELECT 'campvision2.ip', valor, 'IP do computador CAMP Vision 2', 0
  FROM configuracao WHERE chave='campvision.ip';

INSERT OR IGNORE INTO configuracao (chave, valor, descricao, sensivel) VALUES
('qnap.ip','192.168.15.30','IP do QNAP TS-932PX',0),
('qnap.usuario','','Usuário do QNAP para acesso SMB',1),
('qnap.senha','','Senha do QNAP para acesso SMB',1),
('campvision2.ip','192.168.15.40','IP do computador CAMP Vision 2',0),
('campvision2.usuario','','Usuário do CAMP Vision 2 para acesso remoto',1),
('campvision2.senha','','Senha do CAMP Vision 2 para acesso remoto',1),
('estacao.foto1.ip','192.168.15.41','IP da Estação Foto 1',0),
('estacao.foto2.ip','192.168.15.42','IP da Estação Foto 2',0),
('estacao.contex1.ip','192.168.15.43','IP da Estação Contex 1',0),
('estacao.contex2.ip','192.168.15.44','IP da Estação Contex 2',0),
('estacao.universal1.ip','192.168.15.45','IP da Estação Universal 1',0),
('estacao.universal2.ip','192.168.15.46','IP da Estação Universal 2',0);

-- Só preenche os IPs padrão quando o registro já existe, mas ainda está vazio.
UPDATE configuracao SET valor='192.168.15.30' WHERE chave='qnap.ip' AND COALESCE(TRIM(valor),'')='';
UPDATE configuracao SET valor='192.168.15.40' WHERE chave='campvision2.ip' AND COALESCE(TRIM(valor),'')='';
UPDATE configuracao SET valor='192.168.15.41' WHERE chave='estacao.foto1.ip' AND COALESCE(TRIM(valor),'')='';
UPDATE configuracao SET valor='192.168.15.42' WHERE chave='estacao.foto2.ip' AND COALESCE(TRIM(valor),'')='';
UPDATE configuracao SET valor='192.168.15.43' WHERE chave='estacao.contex1.ip' AND COALESCE(TRIM(valor),'')='';
UPDATE configuracao SET valor='192.168.15.44' WHERE chave='estacao.contex2.ip' AND COALESCE(TRIM(valor),'')='';
UPDATE configuracao SET valor='192.168.15.45' WHERE chave='estacao.universal1.ip' AND COALESCE(TRIM(valor),'')='';
UPDATE configuracao SET valor='192.168.15.46' WHERE chave='estacao.universal2.ip' AND COALESCE(TRIM(valor),'')='';

DELETE FROM configuracao WHERE chave='estacao.contex.ip';

-- Remove aliases antigos depois de preservar os valores.
DELETE FROM configuracao WHERE chave='campvision.ip';

-- Padroniza descrições para a tela de configuração.
UPDATE configuracao SET descricao='IP da Estação Foto 1' WHERE chave='estacao.foto1.ip';
UPDATE configuracao SET descricao='IP da Estação Foto 2' WHERE chave='estacao.foto2.ip';
UPDATE configuracao SET descricao='IP da Estação Contex 1' WHERE chave='estacao.contex1.ip';
UPDATE configuracao SET descricao='IP da Estação Contex 2' WHERE chave='estacao.contex2.ip';
UPDATE configuracao SET descricao='IP da Estação Universal 1' WHERE chave='estacao.universal1.ip';
UPDATE configuracao SET descricao='IP da Estação Universal 2' WHERE chave='estacao.universal2.ip';
UPDATE configuracao SET descricao='IP do CAMP Vision 2' WHERE chave='campvision2.ip';
UPDATE configuracao SET descricao='IP do QNAP TS-932PX' WHERE chave='qnap.ip';
