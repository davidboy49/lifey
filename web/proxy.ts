import { NextResponse, type NextRequest } from "next/server";

// First line of defence only: a missing cookie goes straight to /login.
// Whether the session is actually valid is decided by the API on every request.
export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const hasSession = request.cookies.has("lifey_session");

  if (pathname === "/login") {
    return hasSession ? NextResponse.redirect(new URL("/", request.url)) : NextResponse.next();
  }
  if (!hasSession) {
    return NextResponse.redirect(new URL("/login", request.url));
  }
  return NextResponse.next();
}

export const config = {
  // Everything except the API (which answers 401 itself) and Next internals.
  matcher: ["/((?!api/|_next/|favicon.ico).*)"],
};
