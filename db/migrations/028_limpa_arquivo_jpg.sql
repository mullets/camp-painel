-- item.arquivo_jpg recebeu o ID do anexo (ou HTML) do Tainacan em vez do endereço do arquivo.
-- Troca pelo endereço real quando o espelho do site já o tem; senão limpa (a tela cai para wp_item.documento_url).
-- Caminhos locais (começam com /) e URLs http não são tocados.
UPDATE item
   SET arquivo_jpg = (SELECT w.documento_url FROM wp_item w
                       WHERE w.id = item.tainacan_item_id AND w.documento_url LIKE 'http%')
 WHERE arquivo_jpg IS NOT NULL
   AND (arquivo_jpg NOT GLOB '*[^0-9]*' OR arquivo_jpg LIKE '<%');
