import type { Metadata, Viewport } from "next";
import { Bricolage_Grotesque, Geist_Mono, Instrument_Sans } from "next/font/google";
import { Nav } from "@/components/Nav";
import "./globals.css";

const display = Bricolage_Grotesque({ subsets: ["latin"], variable: "--font-display", axes: ["opsz"] });
const body = Instrument_Sans({ subsets: ["latin"], variable: "--font-body" });
const mono = Geist_Mono({ subsets: ["latin"], variable: "--font-mono" });

export const metadata: Metadata = {
  title: "Lifey",
  description: "Your health and money, in one calm place.",
};

export const viewport: Viewport = { viewportFit: "cover", width: "device-width", initialScale: 1 };

// Applies the saved theme before first paint so there is no flash.
const THEME_BOOT = `try{var t=localStorage.getItem("lifey-theme");if(t==="light"||t==="dark")document.documentElement.setAttribute("data-theme",t)}catch(e){}`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${display.variable} ${body.variable} ${mono.variable}`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_BOOT }} />
      </head>
      <body>
        <Nav />
        <main className="px-4 pb-28 pt-6 sm:px-8 md:ml-[232px] md:px-10 md:pb-16 md:pt-10 xl:px-16">
          <div className="mx-auto max-w-[1040px]">{children}</div>
        </main>
      </body>
    </html>
  );
}
