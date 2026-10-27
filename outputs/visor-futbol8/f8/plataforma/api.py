"""Library routes use the same session protection as the other season routes."""
from f8.plataforma.video_library import library_for


def request(app, action, value=None):
    try:
        library = library_for(app)
        return getattr(library, action)() if value is None else getattr(library, action)(value)
    except OSError as error:
        raise ValueError('No se pudo acceder a la biblioteca: ' + str(error)) from error


RUTAS = {
    ('GET', r'/api/season/library'): lambda app, match, query: request(app, 'snapshot'),
    ('GET', r'/api/season/library/catalogue'): lambda app, match, query: request(app, 'catalogue'),
    ('POST', r'/api/season/library/config'): lambda app, match, body: request(app, 'configure', body),
    ('POST', r'/api/season/library/scan'): lambda app, match, body: request(app, 'start_scan'),
    ('POST', r'/api/season/library/examples'): lambda app, match, body: request(app, 'save_examples', body),
}
