import { Link, Outlet } from 'react-router';

export default function AuthLayout() {
  return (
    <main className="grid min-h-screen bg-slate-50 lg:grid-cols-[1.05fr_0.95fr]">
      <section className="hidden bg-slate-950 p-12 text-white lg:flex lg:flex-col lg:justify-between">
        <Link className="text-xl font-black tracking-tight" to="/">UniShop China</Link>
        <div className="max-w-xl">
          <span className="inline-flex rounded-full border border-white/20 bg-white/10 px-3 py-1 text-sm">Marketplace across China</span>
          <h2 className="mt-6 text-5xl font-black leading-tight tracking-tight">Find global products in the city you call home.</h2>
          <p className="mt-5 max-w-lg text-lg leading-8 text-slate-300">Connect with verified sellers, chat safely, and arrange payment and delivery privately.</p>
        </div>
        <p className="text-sm text-slate-400">Community commerce for international residents in China.</p>
      </section>
      <section className="flex min-h-screen flex-col">
        <header className="flex items-center justify-between p-5 sm:px-8">
          <Link className="font-black text-red-600 lg:hidden" to="/">UniShop China</Link>
          <Link className="ml-auto text-sm font-semibold text-slate-600 hover:text-slate-950" to="/">About UniShop</Link>
        </header>
        <div className="flex flex-1 items-center justify-center px-4 pb-12 sm:px-8"><Outlet /></div>
      </section>
    </main>
  );
}
