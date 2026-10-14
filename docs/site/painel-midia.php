<?php
/**
 * Plugin Name: CAMP — rota do painel para trocar a imagem de um anexo
 * Description: Deixa o painel (camp-painel) trocar o ARQUIVO de um anexo de imagem que já existe, mantendo o ID do anexo.
 *              Serve para "Girar folha já publicada": o item do Tainacan, a capa do projeto e os links continuam apontando
 *              para o mesmo anexo, só a imagem muda.
 *
 * AINDA NÃO INSTALADO no site: este arquivo é o contrato. Para valer, copie a rota para o plugin da CAMP (camp-wordpress).
 * Enquanto não estiver lá, o painel responde "O site ainda não tem a rota para trocar a imagem de um anexo" e NÃO grava o giro.
 *
 * POST /wp-json/camp/v1/painel/midia/{id}
 *   corpo: os bytes da imagem (JPEG), com Content-Type: image/jpeg e Content-Disposition: attachment; filename="..."
 *   (o mesmo formato do POST /wp-json/wp/v2/media que o painel já usa para subir imagens novas).
 *   - só para quem pode editar o anexo (current_user_can edit_post), com a Application Password do painel;
 *   - o anexo precisa existir e ser imagem; o corpo precisa ser uma imagem válida;
 *   - grava por cima do arquivo do anexo (mesmo caminho e nome), apaga os tamanhos menores antigos e gera tudo de novo;
 *   - responde {"id": 123, "source_url": "...", "width": 3000, "height": 2000}; 404 se o anexo não existe.
 */
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

add_action( 'rest_api_init', function () {
	register_rest_route( 'camp/v1', '/painel/midia/(?P<id>\d+)', array(
		'methods'             => 'POST',
		'permission_callback' => function ( WP_REST_Request $req ) {
			return current_user_can( 'edit_post', (int) $req['id'] );
		},
		'callback'            => 'camp_painel_trocar_midia',
	) );
} );

function camp_painel_trocar_midia( WP_REST_Request $req ) {
	$id = (int) $req['id'];
	if ( ! $id || 'attachment' !== get_post_type( $id ) || ! wp_attachment_is_image( $id ) ) {
		return new WP_Error( 'camp_sem_anexo', 'Anexo de imagem não encontrado.', array( 'status' => 404 ) );
	}
	$arquivo = get_attached_file( $id );
	if ( ! $arquivo || ! file_exists( $arquivo ) ) {
		return new WP_Error( 'camp_sem_arquivo', 'O arquivo do anexo não está no servidor.', array( 'status' => 404 ) );
	}
	$corpo = $req->get_body();
	if ( '' === $corpo ) {
		return new WP_Error( 'camp_corpo_vazio', 'Nenhuma imagem enviada.', array( 'status' => 400 ) );
	}
	require_once ABSPATH . 'wp-admin/includes/file.php';
	require_once ABSPATH . 'wp-admin/includes/image.php';
	$tmp = wp_tempnam( 'camp-midia' );
	file_put_contents( $tmp, $corpo );
	$info = @getimagesize( $tmp );
	if ( ! $info || IMAGETYPE_JPEG !== $info[2] ) {
		@unlink( $tmp );
		return new WP_Error( 'camp_nao_imagem', 'O corpo não é uma imagem JPEG válida.', array( 'status' => 400 ) );
	}
	// Apaga os tamanhos menores antigos (thumbnail, medium, large...) antes de gravar por cima do original.
	$antigo = wp_get_attachment_metadata( $id );
	if ( is_array( $antigo ) && ! empty( $antigo['sizes'] ) ) {
		$pasta = dirname( $arquivo );
		foreach ( $antigo['sizes'] as $tam ) {
			if ( ! empty( $tam['file'] ) ) {
				@unlink( path_join( $pasta, $tam['file'] ) );
			}
		}
	}
	if ( ! @rename( $tmp, $arquivo ) ) {
		@unlink( $tmp );
		return new WP_Error( 'camp_gravar', 'Não consegui gravar a imagem nova no servidor.', array( 'status' => 500 ) );
	}
	@chmod( $arquivo, 0644 );
	// Sem o "-scaled" automático: o arquivo do anexo já é o que fica no site (o painel manda no tamanho certo).
	add_filter( 'big_image_size_threshold', '__return_false' );
	$meta = wp_generate_attachment_metadata( $id, $arquivo );
	remove_filter( 'big_image_size_threshold', '__return_false' );
	if ( is_array( $antigo ) && ! empty( $antigo['original_image'] ) ) {
		@unlink( path_join( dirname( $arquivo ), $antigo['original_image'] ) );   // a imagem grande antiga, sem giro, não fica para trás
	}
	wp_update_attachment_metadata( $id, $meta );
	clean_post_cache( $id );
	return array(
		'id'         => $id,
		'source_url' => wp_get_attachment_url( $id ),
		'width'      => isset( $meta['width'] ) ? (int) $meta['width'] : null,
		'height'     => isset( $meta['height'] ) ? (int) $meta['height'] : null,
	);
}
