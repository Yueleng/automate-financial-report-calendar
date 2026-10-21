import { redirect } from "next/navigation";

// page.tsx is a special file name.
// A folder under src/app/ becomes a route only if it contains a page.tsx.
// The file at src/app/page.tsx serves /. watchlist/page.tsx serves /watchlist,
// and calendar/page.tsx serves /calendar.

// layout.tsx wraps the pages below it. Next.js renders the matching page.tsx and passes it to the layout as the children prop.
// That is why {children} in layout.tsx is never given an explicit value.
// Layouts nest. The root layout.tsx wraps every page.
// A layout.tsx inside watchlist/ would wrap only that route, and it would sit inside the root layout.
// Other special file names work the same way: loading.tsx, error.tsx, not-found.tsx, route.ts and template.tsx.
// Because of this, tools that look for unused files, such as knip or ts-prune, usually need Next.js entry-point config so they don't flag these files.

// In this app, there is no UI for the homepage, so it redirects to /calendar.
export default function Home() {
  redirect("/calendar");
}
