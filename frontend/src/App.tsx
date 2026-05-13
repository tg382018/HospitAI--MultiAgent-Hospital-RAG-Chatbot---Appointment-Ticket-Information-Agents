import { ChatApp } from './ChatApp';

function App() {
  return (
    <div className="min-h-dvh bg-slate-950 text-slate-100">
      <main className="mx-auto flex max-w-3xl flex-col gap-6 px-4 py-10">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight text-white">HospitAI</h1>
          <p className="mt-1 text-sm text-slate-400">Hasta sohbet — platform API ile bağlı</p>
        </div>
        <ChatApp />
      </main>
    </div>
  );
}

export default App;
