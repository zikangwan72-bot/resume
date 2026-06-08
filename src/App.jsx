import './App.css'

const strengths = [
  '产品设计：精通 Axure、墨刀等原型工具，能够高效完成复杂 B 端业务的产品原型、交互设计及高质量 PRD 文档撰写。',
  '业务经验：3 年互联网 B 端产品经验，深耕企业数字化转型领域，对 ERP、OA 等业务系统有深刻理解和从 0 到 1 的落地经验。',
  '数据驱动：具备完整的数据产品设计经验，包括数据埋点、看板搭建及可视化落地，善于利用数据辅助业务决策与产品迭代。',
  '技术理解：拥有前端开发经验及计算机背景，能与技术团队高效沟通，精准评估技术方案可行性，把控项目风险。',
  '项目管理：具备出色的跨团队协作与项目管理能力，擅长拆解复杂业务需求，制定项目里程碑，并推动产品如期上线。',
  '语言能力：英语可作为工作语言，能够流畅进行英文技术文档协作与会议沟通。',
]

const jobs = [
  {
    company: '浙江悦芯科技有限公司',
    title: '产品经理',
    date: '2025-02 ~ 2026-01',
    items: [
      '主导电网数字化转型项目，参与信息化流程引擎产品设计，通过 AI 审批助手等创新功能，将核心业务流程审批效率提升 75%。',
      '协同多部门完成电网检修、物资采购等 15 个电子化流程设计与系统集成，实现审批业务全线拉通。',
    ],
  },
  {
    company: '比亚迪集团',
    title: '产品经理',
    date: '2022-07 ~ 2025-01',
    items: [
      '主导从 0 到 1 打造资产管理系统、绩效评价系统等 B 端产品，实现业务全流程线上闭环，累计节省集团成本超百万元。',
      '负责资产管理系统规划与迭代，引入考核机制推动资产异常数量降低 31.6%，年度节约成本 200 余万元。',
    ],
  },
]

const projects = [
  {
    name: '陕电流程审批中心',
    parts: [
      ['项目背景', '为响应电网数字化转型，深度参与建设集团统一流程引擎，完成电网检修、物资采购、项目立项等核心审批业务的全链路梳理与标准化设计，构建覆盖全业务的审批枢纽。'],
      ['需求调研', '作为项目负责人，协同调度、设备、营销等核心生产部门进行多轮对接，输出体系化的电网业务流程模板库。'],
      ['功能设计', '独立负责电网检修申请、项目物资采购、技改立项等 15 个电子化流程的产品设计与迭代，主导设计电网物资采购数据看板，实现从需求到履约的全流程可视化监控。'],
      ['系统优化', '推动 AI 审批助手落地，实现审批意见自动生成，单流程平均审批时效缩短 75%。'],
      ['取得成果', '流程覆盖半数以上电网物资采购业务，累计处理超 20 万条；采购看板为物资集约化管理提供实时决策支持，并将月度统计人力消耗降为 0。'],
    ],
  },
  {
    name: '资产管理系统',
    parts: [
      ['项目背景', '本产品为集团提供统一的全资产管理及办公资产管理平台，通过资产台账管理、全员扫码盘点、资产过程管理等功能，大幅降低资产盘点难度，提升资产管理效率。'],
      ['方案制定', '对市场上的资产管理产品进行竞品分析，对业务部门进行调研，输出具体产品规划方案，包括资产台账管理、全员扫码盘点、资产过程管理等功能。'],
      ['功能设计', '根据上市产品规划方案中所涉及到的具体模块输出产品原型、产品流程图、PRD 文档，经过开发上线、业务团队试用后，业务运行效率相比提升 80%，问题解决率达到 100%。'],
      ['迭代优化', '通过项目上线后的运营调研，迭代设计资产管理黑榜，依照每季度资产异常数量对部门进行排名并公示，经两季度相关资产异常数量降低 31.6%。'],
      ['取得成果', '通过对资产系统的建设，节约公司成本 200 余万元，资产部门团队工作效率提高 50%。'],
    ],
  },
]

function Section({ title, children }) {
  return (
    <section className="section">
      <h2>{title}</h2>
      {children}
    </section>
  )
}

function App() {
  return (
    <main className="resume-page">
      <header className="hero">
        <div className="hero-copy">
          <h1>万秭康</h1>
          <p>求职意向：产品经理 ｜ 西安 ｜ 随时到岗</p>
          <p>25岁 ｜ 4年经验</p>
          <p>15104578031 ｜ 1453357093@qq.com</p>
        </div>
        <div className="photo-placeholder" aria-label="头像占位">
          <span>照片</span>
        </div>
      </header>

      <Section title="教育背景">
        <div className="row-title">
          <strong>黑龙江大学 - 计算机科学与技术 - 本科</strong>
          <span>2018-09 ~ 2022-06</span>
        </div>
        <p>主修学科：Java 程序设计、Web 前端开发、数据库应用、数据结构、人工智能基础、深度学习等。</p>
      </Section>

      <Section title="个人优势">
        <ul>
          {strengths.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </Section>

      <Section title="工作经验">
        {jobs.map((job) => (
          <article className="block" key={job.company}>
            <div className="row-title">
              <strong>
                {job.company} - {job.title}
              </strong>
              <span>{job.date}</span>
            </div>
            <ul>
              {job.items.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </article>
        ))}
      </Section>

      <Section title="项目经验">
        {projects.map((project) => (
          <article className="block" key={project.name}>
            <h3>{project.name}</h3>
            <ul>
              {project.parts.map(([label, text]) => (
                <li key={label}>
                  <strong>{label}：</strong>
                  {text}
                </li>
              ))}
            </ul>
          </article>
        ))}
      </Section>
    </main>
  )
}

export default App
