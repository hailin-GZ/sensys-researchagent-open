"""Installation facts for model tool discovery; never infer integration from a catalog."""
import importlib.util
from pathlib import Path
from .public_data import ROUTES as PUBLIC_DATA_ROUTES

PLATFORM_ROUTES=('google_play_reviews','rss','discourse_thread','hackernews','hackernews_comments','crossref','pubmed','pubmed_abstract','europepmc_search','europepmc_fulltext',*PUBLIC_DATA_ROUTES)
DEPENDENCIES={'google_play_reviews':('google_play_scraper',),'rss':('feedparser',),'search_sources':('ddgs','openai'),'capture_sources':('requests','bs4','pypdf'),'browser_capture':('playwright',)}

def installation(card,skill,routes):
    route=routes.get(card['id']);missing=[]
    for module in DEPENDENCIES.get(route,()):
        if importlib.util.find_spec(module) is None:missing.append(module)
    if route=='browser_capture':
        try:
            from browser_path import chromium_path
            chromium_path()
        except (ImportError,ValueError):missing.append('Chromium executable')
    rel=card.get('package_path');path=(Path(skill)/rel).resolve() if isinstance(rel,str) else None
    present=bool(path and path.is_relative_to(Path(skill).resolve()) and path.is_file())
    if route:
        state='missing_dependency' if missing else 'registered'
        note='Install the missing dependencies before use.' if missing else 'Registered handler and local dependencies exist; acquisition succeeds only if the actual public target is accessible. This does not grant private/account access.'
    elif present and card.get('availability')=='bundled_instructions':
        state='bundled_method';note='Bundled method reference is present; select this package_path through load_methods. Host policy and approved tools govern use; any external connector described in the text still needs its own actual integration and authorization.'
    elif present:
        state='unregistered_local_file';note='Local file exists but no catalog-specific execution route is registered. Do not run arbitrary commands; use an approved handler if it covers the need.'
    elif card.get('availability')=='host_only':
        state='host_only';note='Desktop host capability is not installed in the customer agent. No execution route is registered.'
    else:
        state='catalog_only';note='Discovery record only: no local package or catalog-specific handler. Do not claim it is installed, authorized or executable. A public website may still be acquired through capture_sources; account APIs require separate integration.'
    return {'registered_route':route,'installation_state':state,'package_present':present,'missing_dependencies':missing,'runtime_note':note}
