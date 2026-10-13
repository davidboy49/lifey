import { BackupAlert } from "@/components/BackupAlert";
import { Nav } from "@/components/Nav";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <Nav />
      <main className="px-4 pb-28 pt-6 sm:px-8 md:ml-[232px] md:px-10 md:pb-16 md:pt-10 xl:px-16">
        <BackupAlert />
        <div className="mx-auto max-w-[1040px]">{children}</div>
      </main>
    </>
  );
}
