import re


def test_docs_and_assets_work_without_cdn(client):
    response = client.get('/docs')
    assert response.status_code == 200
    assets = re.findall(r'(?:src|href)="([^"]+)"', response.text)
    assert assets
    for url in assets:
        assert url.startswith('/docs-assets/')
        asset = client.get(url)
        assert asset.status_code == 200
        assert len(asset.content) > 0
        assert 'text/html' not in asset.headers['content-type']
    schema = client.get('/openapi.json')
    assert schema.status_code == 200
    assert '/api/goals' in schema.json()['paths']
    assert '/docs' not in schema.json()['paths']
    assert client.get('/docs/oauth2-redirect').status_code == 200
