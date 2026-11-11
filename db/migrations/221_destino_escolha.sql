-- 11/11/2026 (Rafael: "eu não tenho opção para fazer nada, por que fica me pedindo para verificar algo?"): o lote ficava "movendo" para
-- sempre quando o CAMP Vision NÃO movia a pasta (o carimbo combinava com dois projetos). Agora uma pessoa escolhe o projeto certo e a
-- escolha vai para a mesma lista que o CAMP Vision lê (GET /api/campvision/destinos), que move a pasta sozinho.
-- Também a decisão "É de outro projeto" (lote_destino) entra nesta lista. NULL = decidido pelo painel (UX-43), como antes.
ALTER TABLE destino_auto ADD COLUMN escolhido_por TEXT;
ALTER TABLE destino_auto ADD COLUMN escolhido_em TEXT;
