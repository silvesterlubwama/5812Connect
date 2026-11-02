/**
 * Each organisation lives under its own web name: 5812uganda.org/lub, and every
 * page of the app sits beneath it — 5812uganda.org/lub/members.
 *
 * The router gets that web name as its basename, so every link in the app stays
 * written as /members and still lands in the right organisation. Requests carry
 * the same name in X-Org-Slug so the server knows whose data to answer with
 * before anybody has signed in.
 */
const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;

let currentSlug = '';

export const getOrgSlug = () => currentSlug;

export const setOrgSlug = (slug) => {
  currentSlug = (slug || '').toLowerCase();
};

/** The first part of the path, which is where the web name lives. */
export const firstPathSegment = () =>
  (window.location.pathname.split('/')[1] || '').toLowerCase();

/** Everything after the web name, kept as-is so a shared deep link survives. */
export const pathAfterSegment = () => {
  const rest = window.location.pathname.split('/').slice(2).join('/');
  return `/${rest}${window.location.search}${window.location.hash}`;
};

/** Open another organisation — a full load, because the router's basename
 *  is fixed for the life of the page. */
export const goToOrg = (slug, path = '/') => {
  window.location.href = `/${slug}${path.startsWith('/') ? path : `/${path}`}`;
};

/**
 * Ask the server which organisation this address belongs to. Returns the web
 * name to run under, or null while it is redirecting.
 */
export const resolveOrgRoute = async () => {
  const segment = firstPathSegment();
  const res = await fetch(
    `${BACKEND_URL}/api/public/org-route?segment=${encodeURIComponent(segment)}`,
  );
  if (!res.ok) throw new Error('could not reach the server');
  const data = await res.json();

  if (data.found && !data.suspended) {
    setOrgSlug(data.slug);
    return data.slug;
  }
  if (data.found && data.suspended) {
    setOrgSlug(data.slug);
    return data.slug; // the app shows the suspension message
  }
  // Not a web name — an old link such as /members, or the bare domain. Move it
  // under the default organisation and keep whatever came after it.
  const fallback = data.default_slug;
  if (!fallback) throw new Error('no organisation is set up yet');
  const keep = segment ? window.location.pathname : '/';
  window.location.replace(`/${fallback}${keep}${window.location.search}${window.location.hash}`);
  return null;
};
