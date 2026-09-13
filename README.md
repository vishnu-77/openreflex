# OpenReflex website

Landing page for [OpenReflex](https://github.com/vishnu-77/openreflex), muscle memory for AI coding agents.

This branch contains only the site. It is a statically exported Next.js app, deployed by Vercel from the
`website` branch.

```bash
npm ci
npm run dev      # http://localhost:3000
npm run build    # static export to out/
```

Set `NEXT_PUBLIC_SITE_URL` to the production URL so canonical, Open Graph and sitemap links are absolute.
