import { Bot, Brain, FileText, GraduationCap, Library, Network, Sparkles, GitCompare } from "lucide-react";
import { APP_VERSION } from "@/lib/app-version";

const features = [
  { icon: GraduationCap, title: "深度解题", desc: "面向数学/理科题的多步推理链路，支持图片题、规划、解答、复盘。" },
  { icon: Network, title: "知识图谱", desc: "把知识点、章节、阅读材料结构化，帮助学生看见知识之间的关系。" },
  { icon: Library, title: "课外书学习", desc: "可把课外书、阅读材料、讲义纳入学习资料，再用于总结、问答和图谱化。" },
  { icon: Bot, title: "辅导机器人", desc: "创建不同学科/人格的 TutorBot，用于指定场景的陪伴式学习。" },
  { icon: FileText, title: "共写与笔记", desc: "支持写作辅助、读书笔记、学习记录和内容整理。" },
  { icon: Brain, title: "记忆与个性化", desc: "围绕学习过程沉淀上下文，让后续辅导更贴近个人情况。" },
];

const differences = [
  "品牌和产品方向从 DeepTutor 改为 IntelliTutor：面向真实学生学习场景，而不是只做通用 demo。",
  "新增用户注册登录、邀请注册和部署版访问控制，适合小规模试用。",
  "新增/强化知识图谱、课外书学习、辅导机器人、共写和学习工作台入口。",
  "前端重做为更完整的学习产品界面，增加版本编号，方便确认线上是否为最新版本。",
  "后端接入 Intellicode / GPT-5.x 等模型配置，更贴合当前部署环境。",
];

export default function FeaturesPage() {
  return (
    <div className="mx-auto max-w-5xl px-6 py-10">
      <div className="mb-8 rounded-2xl border border-[var(--border)] bg-[var(--card)] p-7">
        <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-[var(--border)] px-3 py-1 text-xs text-[var(--muted-foreground)]">
          <Sparkles className="h-3.5 w-3.5" /> 当前版本 {APP_VERSION}
        </div>
        <h1 className="text-3xl font-semibold tracking-tight text-[var(--foreground)]">IntelliTutor 功能说明</h1>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-[var(--muted-foreground)]">
          IntelliTutor 基于 DeepTutor 做了产品化改造：从“开源学习助手框架”变成面向学生、老师和家庭试用的学习工作台。
        </p>
      </div>

      <section className="mb-6 rounded-2xl border border-[var(--border)] bg-[var(--card)] p-6">
        <div className="mb-4 flex items-center gap-2">
          <GitCompare className="h-5 w-5 text-[var(--foreground)]" />
          <h2 className="text-lg font-medium text-[var(--foreground)]">我们和原版 DeepTutor 有什么不同？</h2>
        </div>
        <ul className="space-y-2 text-sm leading-6 text-[var(--muted-foreground)]">
          {differences.map((item) => <li key={item}>• {item}</li>)}
        </ul>
      </section>

      <div className="grid gap-4 md:grid-cols-2">
        {features.map((feature) => {
          const Icon = feature.icon;
          return (
            <section key={feature.title} className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-5">
              <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-xl bg-[var(--muted)] text-[var(--foreground)]">
                <Icon className="h-5 w-5" />
              </div>
              <h2 className="text-base font-medium text-[var(--foreground)]">{feature.title}</h2>
              <p className="mt-2 text-sm leading-6 text-[var(--muted-foreground)]">{feature.desc}</p>
            </section>
          );
        })}
      </div>

      <section className="mt-6 rounded-2xl border border-[var(--border)] bg-[var(--card)] p-6">
        <h2 className="text-lg font-medium text-[var(--foreground)]">课外书如何进入知识图谱？</h2>
        <ol className="mt-3 list-decimal space-y-2 pl-5 text-sm leading-6 text-[var(--muted-foreground)]">
          <li>进入 Book 或 Knowledge 页面，上传/整理课外书材料。</li>
          <li>确认材料已进入知识库后，打开 Knowledge Graph。</li>
          <li>输入“为这本书生成知识图谱/人物关系/章节结构”，即可生成图谱化视图。</li>
        </ol>
      </section>
    </div>
  );
}
