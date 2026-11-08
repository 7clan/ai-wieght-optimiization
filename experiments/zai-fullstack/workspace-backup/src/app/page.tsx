'use client';

import { useState } from 'react';
import Image from 'next/image';
import {
  Card, CardContent, CardDescription, CardHeader, CardTitle,
} from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { cn } from '@/lib/utils';

const stats = [
  { label: 'TaskFlow v2 browser tests', value: '15/15', tone: 'emerald' },
  { label: 'TaskFlow v2 visual metrics', value: '10/10', tone: 'emerald' },
  { label: 'MediVault browser tests', value: '10/10', tone: 'violet' },
  { label: 'MediVault visual metrics', value: '10/10', tone: 'violet' },
] as const;

const provenance = [
  { app: 'TaskFlow v2', qwenOriginal: 10, qwenRepaired: 8, teacher: 1, scaffolding: 1 },
  { app: 'MediVault Lite', qwenOriginal: 1, qwenRepaired: 8, teacher: 1, scaffolding: 1 },
];

function Metric({ label, value, tone }: { label: string; value: string; tone: string }) {
  return (
    <div className="rounded-lg border bg-card p-4 text-center">
      <div
        className={cn(
          'text-2xl font-bold tabular-nums',
          tone === 'emerald' && 'text-emerald-600 dark:text-emerald-400',
          tone === 'violet' && 'text-violet-600 dark:text-violet-400'
        )}
      >
        {value}
      </div>
      <div className="mt-1 text-xs text-muted-foreground">{label}</div>
    </div>
  );
}

export default function Home() {
  const [liveApp, setLiveApp] = useState<'taskflow' | 'medivault'>('taskflow');

  return (
    <div className="min-h-screen flex flex-col bg-background text-foreground">
      <header className="border-b bg-card">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-3 px-4 py-4">
          <span className="text-xl font-bold tracking-tight">
            <span className="text-emerald-600 dark:text-emerald-400">●</span> Qwen Architect
          </span>
          <Badge variant="secondary">Session 034</Badge>
          <div className="flex-1" />
          <Badge variant="outline">Frozen Qwen2.5-Coder-0.5B</Badge>
        </div>
      </header>

      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8">
        <section className="mb-10">
          <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">
            Visual Intelligence &amp; Full-Stack Generalization
          </h1>
          <p className="mt-3 max-w-3xl text-muted-foreground">
            Two complete web applications generated under a frozen 0.5B code model,
            verified in a real browser: <strong>TaskFlow v2</strong> (project management,
            professional SaaS styling) and <strong>MediVault Lite</strong> (medical records
            vault, independent visual identity). Every measurement below comes from
            automated Playwright runs against the running apps.
          </p>
          <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
            {stats.map((s) => (
              <Metric key={s.label} {...s} />
            ))}
          </div>
        </section>

        <Tabs defaultValue="taskflow" className="mb-10">
          <TabsList className="max-w-full flex-wrap">
            <TabsTrigger value="taskflow">TaskFlow v2</TabsTrigger>
            <TabsTrigger value="medivault">MediVault Lite</TabsTrigger>
          </TabsList>

          <TabsContent value="taskflow" className="mt-4">
            <div className="grid gap-6 lg:grid-cols-2">
              <Card>
                <CardHeader>
                  <CardTitle>Desktop · 1440×900 (real screenshot)</CardTitle>
                  <CardDescription>
                    Sidebar projects, status badges, progress bar, search &amp; filter.
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <Image
                    src="/shots/taskflow-desktop.png"
                    alt="TaskFlow v2 desktop screenshot"
                    width={1440}
                    height={900}
                    className="rounded-lg border h-auto w-full"
                    priority
                    unoptimized
                  />
                </CardContent>
              </Card>
              <Card>
                <CardHeader>
                  <CardTitle>Mobile · 390×844 (real screenshot)</CardTitle>
                  <CardDescription>
                    Slide-in sidebar via menu button, full-width task grid.
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <Image
                    src="/shots/taskflow-mobile.png"
                    alt="TaskFlow v2 mobile screenshot"
                    width={390}
                    height={844}
                    className="rounded-lg border h-auto w-full"
                    unoptimized
                  />
                </CardContent>
              </Card>
            </div>
          </TabsContent>

          <TabsContent value="medivault" className="mt-4">
            <div className="grid gap-6 lg:grid-cols-2">
              <Card>
                <CardHeader>
                  <CardTitle>Desktop · 1440×900 (real screenshot)</CardTitle>
                  <CardDescription>
                    Folder tabs, records table, type badges, metadata detail modal.
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <Image
                    src="/shots/medivault-desktop.png"
                    alt="MediVault Lite desktop screenshot"
                    width={1440}
                    height={900}
                    className="rounded-lg border h-auto w-full"
                    unoptimized
                  />
                </CardContent>
              </Card>
              <Card>
                <CardHeader>
                  <CardTitle>Mobile · 390×844 (real screenshot)</CardTitle>
                  <CardDescription>
                    Scrollable records table, wrapping header controls.
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <Image
                    src="/shots/medivault-mobile.png"
                    alt="MediVault Lite mobile screenshot"
                    width={390}
                    height={844}
                    className="rounded-lg border h-auto w-full"
                    unoptimized
                  />
                </CardContent>
              </Card>
            </div>
          </TabsContent>
        </Tabs>

        <section className="mb-10">
          <h2 className="mb-3 text-xl font-semibold">Try the live apps</h2>
          <Card>
            <CardContent className="pt-6">
              <div className="mb-3 flex flex-wrap items-center gap-2">
                <Button
                  variant={liveApp === 'taskflow' ? 'default' : 'outline'}
                  onClick={() => setLiveApp('taskflow')}
                >
                  TaskFlow v2
                </Button>
                <Button
                  variant={liveApp === 'medivault' ? 'default' : 'outline'}
                  onClick={() => setLiveApp('medivault')}
                >
                  MediVault Lite
                </Button>
                <div className="flex-1" />
                <a
                  href={liveApp === 'taskflow' ? '/taskflow-v2/index.html' : '/medivault/index.html'}
                  target="_blank"
                  rel="noreferrer"
                >
                  <Button variant="ghost">Open in new tab ↗</Button>
                </a>
              </div>
              <div className="overflow-hidden rounded-lg border">
                <iframe
                  key={liveApp}
                  src={liveApp === 'taskflow' ? '/taskflow-v2/index.html' : '/medivault/index.html'}
                  title={liveApp === 'taskflow' ? 'TaskFlow v2 live app' : 'MediVault Lite live app'}
                  className="h-[560px] w-full bg-white"
                />
              </div>
              <p className="mt-2 text-xs text-muted-foreground">
                Both apps run entirely in your browser (React via Babel standalone, data in
                localStorage). Reload to reset the seeded demo data.
              </p>
            </CardContent>
          </Card>
        </section>

        <section className="mb-10">
          <h2 className="mb-3 text-xl font-semibold">Who wrote what (provenance)</h2>
          <Card>
            <CardContent className="pt-6">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-left text-xs uppercase tracking-wide text-muted-foreground">
                      <th className="pb-2 pr-4">App</th>
                      <th className="pb-2 pr-4">Qwen original</th>
                      <th className="pb-2 pr-4">Qwen + bounded repairs</th>
                      <th className="pb-2 pr-4">Teacher (integration)</th>
                      <th className="pb-2">Scaffolding</th>
                    </tr>
                  </thead>
                  <tbody>
                    {provenance.map((p) => (
                      <tr key={p.app} className="border-b last:border-0">
                        <td className="py-2.5 pr-4 font-medium">{p.app}</td>
                        <td className="py-2.5 pr-4"><Badge className="bg-emerald-100 text-emerald-800 hover:bg-emerald-100">{p.qwenOriginal}</Badge></td>
                        <td className="py-2.5 pr-4"><Badge className="bg-amber-100 text-amber-800 hover:bg-amber-100">{p.qwenRepaired}</Badge></td>
                        <td className="py-2.5 pr-4"><Badge className="bg-rose-100 text-rose-800 hover:bg-rose-100">{p.teacher}</Badge></td>
                        <td className="py-2.5"><Badge variant="secondary">{p.scaffolding}</Badge></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <Separator className="my-4" />
              <p className="text-xs leading-relaxed text-muted-foreground">
                &ldquo;Qwen original&rdquo; = generated by the frozen model, accepted as-is after
                syntax + contract validation. &ldquo;Bounded repairs&rdquo; = Qwen base with
                teacher fixes for defects caught by browser tests (each repair documented in the
                file header and ORIGIN.json). Teacher work never counts as model capability;
                the model could not produce the integration layer (app state wiring) within
                budget in either app — that limitation is part of the findings.
              </p>
            </CardContent>
          </Card>
        </section>

        <section className="mb-4">
          <h2 className="mb-3 text-xl font-semibold">Key finding</h2>
          <Card>
            <CardHeader>
              <CardTitle>Unassisted single-shot vs. the full harness</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm leading-relaxed text-muted-foreground">
                Given the identical TaskFlow requirements in one prompt (Track A), the same
                frozen model stopped after ~107&ndash;1600 tokens across 7 candidates; the best
                result was a truncated single file that rendered a title but{' '}
                <strong>zero interactive elements</strong> in a real browser. With staged
                specs, mechanical assembly, feedback loops and three visual-correction rounds
                (Track D), the same model produced a 15/15-functional, 98%-visual application.
                The gap is the system, not the weights.
              </p>
            </CardContent>
          </Card>
        </section>
      </main>

      <footer className="mt-auto border-t bg-card">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-4 gap-y-1 px-4 py-4 text-xs text-muted-foreground">
          <span>PROJECT QWEN ARCHITECT · Session 034</span>
          <span aria-hidden>·</span>
          <span>Frozen Qwen/Qwen2.5-Coder-0.5B-Instruct (no training, no fine-tuning)</span>
          <span aria-hidden>·</span>
          <span>All tests &amp; screenshots from real Playwright runs</span>
        </div>
      </footer>
    </div>
  );
}
