<?php
/**
 * Plugin Name: CAMP — rota do painel para a página-hub do arquiteto
 * Description: Deixa o painel (camp-painel) gravar os campos "Sobre o acervo", a biografia e o retrato da página-hub
 *              de um fundo. Cartões B1 e B9 do quadro do painel (13/10/2026).
 *
 * INSTALAR: copiar este arquivo para wp-content/mu-plugins/ do site (ou colar no fim do plugin camp-acervo-auto-pages).
 * Não muda nada sozinho: só responde quando o painel chama, com a Application Password de um usuário que pode editar páginas.
 *
 * POST /wp-json/camp/v1/painel/hub/{term_id}   corpo: {"meta": {"_camp_acervo_procedencia": "…", …}}
 *   - só aceita as chaves da lista abaixo; texto vazio APAGA o campo (volta ao padrão do site);
 *   - _camp_foto_id precisa ser um anexo de imagem que já existe (o painel sobe a foto em /wp/v2/media antes);
 *   - responde {"ok": true, "page_id": 123, "gravados": [...], "apagados": [...]}; 404 se o fundo ainda não tem página-hub.
 */
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

add_action( 'rest_api_init', function () {
	register_rest_route( 'camp/v1', '/painel/hub/(?P<term_id>\d+)', array(
		'methods'             => 'POST',
		'permission_callback' => function () {
			return current_user_can( 'edit_pages' );
		},
		'callback'            => 'camp_painel_gravar_hub',
	) );
} );

function camp_painel_gravar_hub( WP_REST_Request $req ) {
	$texto = array(
		'_camp_acervo_periodo', '_camp_acervo_extensao', '_camp_acervo_historico', '_camp_acervo_procedencia',
		'_camp_acervo_ingresso', '_camp_acervo_doador', '_camp_acervo_acesso', '_camp_acervo_descricao',
		'_camp_bio', '_camp_bio_fontes',
	);
	$term_id = (int) $req['term_id'];
	$page_id = class_exists( 'Camp_AAP_Data' ) ? Camp_AAP_Data::hub_page_for_term( $term_id ) : 0;
	if ( ! $page_id ) {
		return new WP_Error( 'camp_sem_hub', 'Este fundo ainda não tem página-hub no site.', array( 'status' => 404 ) );
	}
	$meta = (array) $req->get_param( 'meta' );
	$gravados = array();
	$apagados = array();
	foreach ( $meta as $chave => $valor ) {
		if ( '_camp_foto_id' === $chave ) {
			$foto = (int) $valor;
			if ( ! $foto ) {
				delete_post_meta( $page_id, '_camp_foto_id' );
				$apagados[] = $chave;
			} elseif ( wp_attachment_is_image( $foto ) ) {
				update_post_meta( $page_id, '_camp_foto_id', $foto );
				$gravados[] = $chave;
			} else {
				return new WP_Error( 'camp_foto_invalida', 'O retrato precisa ser uma imagem da biblioteca de mídia.', array( 'status' => 400 ) );
			}
			continue;
		}
		if ( ! in_array( $chave, $texto, true ) ) {
			continue;
		}
		$valor = sanitize_textarea_field( (string) $valor );
		if ( '' === trim( $valor ) ) {
			delete_post_meta( $page_id, $chave );
			$apagados[] = $chave;
		} else {
			update_post_meta( $page_id, $chave, $valor );
			$gravados[] = $chave;
		}
	}
	return array( 'ok' => true, 'page_id' => $page_id, 'gravados' => $gravados, 'apagados' => $apagados );
}
