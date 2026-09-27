import React, {useEffect, useState} from 'react';
import {AbsoluteFill, Img, Sequence, cancelRender, continueRender, delayRender, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import './styles.css';

const C = {paper: '#f6f3e9', ink: '#203e34', muted: '#7d8979', gold: '#b39751', green: '#2f5947', line: '#d9decb', sage: '#e7ecdc', paleGold: '#e9dfbb'};
const FONT = '"Dawn Sans", sans-serif';
const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'};

function Mark({size = 62, color = C.gold}) {
  return <svg width={size} height={size} viewBox="0 0 64 64" fill="none" style={{flexShrink: 0}}>
    <path d="M8 48h48M13 55h38M17 42a15 15 0 0 1 30 0M13 34l-6-3M21 23l-4-6M32 20V11M43 23l4-6M51 33l6-3" stroke={color} strokeWidth="1.7" strokeLinecap="round"/>
    <path d="M24 44c2-9 10-13 18-17-1 8-6 13-13 16" stroke={color} strokeWidth="1.7" strokeLinecap="round"/>
  </svg>;
}

function Brand({dark = false, compact = false}) {
  return <div style={{display: 'flex', alignItems: 'center', gap: 17}}>
    <Mark size={compact ? 47 : 60}/>
    <div><div style={{fontSize: compact ? 24 : 30, letterSpacing: 7, color: dark ? C.paper : C.ink, fontWeight: 500}}>黎明工坊</div><div style={{fontSize: 10, letterSpacing: 5, color: C.gold, marginTop: 8}}>DAWN ATELIER</div></div>
  </div>;
}

function Leaf({left, top, scale = 1, opacity = .25, rotation = 0}) {
  return <svg width={340} height={390} viewBox="0 0 340 390" style={{position: 'absolute', left, top, opacity, transform: `rotate(${rotation}deg) scale(${scale})`}} fill="none">
    <path d="M60 350C180 302 228 197 240 46M182 230C113 231 87 192 77 155c58-1 90 28 106 66M210 160c58-9 89-43 93-76-55 4-81 33-93 76M146 290c-60 5-99-23-120-56 65-15 102 15 120 56M234 85c-42-17-55-43-52-69 40 18 52 43 52 69" stroke={C.gold} strokeWidth="1.5"/>
  </svg>;
}

function Backdrop({dark = false}) {
  const f = useCurrentFrame();
  return <AbsoluteFill style={{background: dark ? C.ink : C.paper, overflow: 'hidden'}}>
    <div style={{position: 'absolute', width: 1070, height: 1070, borderRadius: '50%', left: 1220, top: -455, background: dark ? '#2a4b3f' : '#ebe9d8', opacity: .7, transform: `translateY(${Math.sin(f/160)*7}px)`}}/>
    <div style={{position: 'absolute', width: 1310, height: 1310, borderRadius: '50%', left: 1090, top: -580, border: `1px solid ${dark ? '#43634c' : '#dce0ca'}`}}/>
    <Leaf left={1530} top={655} opacity={dark ? .28 : .2} rotation={-15}/>
    <div style={{position: 'absolute', left: 100, top: 146, right: 100, height: 1, background: dark ? '#4c6350' : C.line}}/>
  </AbsoluteFill>;
}

function Window({asset, left, top, width, height, crop = false, scale = 1, origin = 'top left', border = true}) {
  const imageStyle = asset === 'preview'
    ? {position: 'absolute', width: '134%', maxWidth: 'none', left: '-17%', top: -316}
    : crop ? {position: 'absolute', width: '121.5%', maxWidth: 'none', left: '-19.1%', top: -96}
    : {width: '100%', display: 'block'};
  return <div style={{position: 'absolute', left, top, width, height, borderRadius: 18, overflow: 'hidden', background: C.paper, border: border ? '1px solid #d8ddc7' : 0, boxShadow: '0 30px 75px #15372b20', transform: `scale(${scale})`, transformOrigin: origin}}>
    <div style={{height: 34, background: '#eeefe5', borderBottom: `1px solid ${C.line}`, display: 'flex', alignItems: 'center', gap: 6, padding: '0 15px'}}>
      {[C.gold,'#9cac88','#bec5b4'].map((color) => <span key={color} style={{width: 7, height: 7, borderRadius: '50%', background: color}}/>)}
      <span style={{fontSize: 10, letterSpacing: 2.5, color: '#8b9581', marginLeft: 12}}>DAWN ATELIER</span>
    </div>
    <div style={{position: 'relative', height: height - 34, overflow: 'hidden'}}>
      <Img src={staticFile(`${asset}.png`)} style={imageStyle}/>
    </div>
  </div>;
}

function SmallLabel({children}) {
  return <div style={{display: 'flex', gap: 14, alignItems: 'center', fontSize: 14, letterSpacing: 4, fontWeight: 500, color: C.gold}}><span style={{width: 36, height: 1, background: C.gold}}/>{children}</div>;
}

function Tag({children, index = 0}) {
  const f = useCurrentFrame();
  return <div style={{padding: '12px 19px', border: `1px solid ${C.line}`, background: '#ffffff60', borderRadius: 30, fontSize: 18, color: C.green, opacity: interpolate(f,[24+index*5,38+index*5],[0,1],clamp), transform: `translateY(${interpolate(f,[24+index*5,38+index*5],[9,0],clamp)}px)`}}>{children}</div>;
}

const CHAPTERS = [
  {from: 0, duration: 150, id: '01', name: '你的冒险，你的节奏', type: 'intro'},
  {from: 135, duration: 180, id: '02', name: '一键方案', title: ['从一个方案', '开始。'], description: ['选择喜欢的游玩节奏，', '把常用调整一次准备好。'], asset: 'presets', tags: ['轻松开荒','田园日常','富足经营'], marker: 'START WITH A PLAN'},
  {from: 300, duration: 150, id: '03', name: '背包与物品', title: ['行囊，', '按心意整理。'], description: ['查找需要的物品，', '清楚设置每一项数量。'], asset: 'inventory', tags: ['搜索物品','调整数量','预览变更'], marker: 'A LITTLE MORE PREPARED'},
  {from: 435, duration: 135, id: '04', name: 'NPC 与好感', title: ['让每段相遇，', '都有回响。'], description: ['按角色查看好感度，', '为想要的关系设定目标。'], asset: 'relationships', tags: ['角色列表','好感目标'], marker: 'ROOM FOR EVERY STORY'},
  {from: 555, duration: 150, id: '05', name: '工具升级', title: ['熟悉的工具，', '更顺手。'], description: ['工具等级一目了然，', '逐项准备升级方案。'], asset: 'tools', tags: ['当前等级','目标等级'], marker: 'READY FOR TOMORROW'},
  {from: 690, duration: 180, id: '06', name: '预览与备份', title: ['每次调整，', '都先看清楚。'], description: ['核对方案与调整项目，', '带着备份，再开启新一天。'], asset: 'preview', tags: ['方案预览','导出备份'], marker: 'MAKE EVERY CHANGE CLEAR'},
  {from: 855, duration: 105, id: '07', name: '黎明工坊', type: 'outro'},
];

function Footer({chapter, dark = false}) {
  return <div style={{position: 'absolute', left: 100, right: 100, bottom: 40, display: 'flex', alignItems: 'center', justifyContent: 'space-between', color: dark ? '#b2c0a8' : C.muted}}>
    <span style={{fontSize: 12, letterSpacing: 1.5}}>演示数据 · 编辑器与变更预览</span>
    <div style={{display: 'flex', alignItems: 'center', gap: 18}}><span style={{fontSize: 13, letterSpacing: 2}}>{chapter.name}</span><span style={{color: C.gold, fontSize: 13}}>{chapter.id} / 07</span></div>
  </div>;
}

function Intro() {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const appear = spring({frame: f - 8, fps, config: {damping: 25, mass: 1.05, stiffness: 105}});
  return <>
    <div style={{position: 'absolute', left: 100, top: 270, opacity: interpolate(f,[8,28],[0,1],clamp), transform: `translateY(${(1-appear)*24}px)`}}>
      <SmallLabel>A NEW DAY, YOUR WAY</SmallLabel>
      <div style={{fontSize: 72, fontWeight: 450, letterSpacing: -2, lineHeight: 1.5, marginTop: 37}}>把冒险，<br/>调成喜欢的样子。</div>
      <div style={{fontSize: 24, color: C.muted, lineHeight: 1.9, marginTop: 30}}>你的本地存档工作台。<br/>从整理行囊，到规划下一段旅程。</div>
      <div style={{marginTop: 43, display: 'flex', alignItems: 'center', gap: 16, fontSize: 17, color: C.green}}><span style={{width: 7, height: 7, background: '#819b6b', borderRadius: '50%'}}/>本地运行 <span style={{opacity: .4}}>／</span> 先预览，再导出</div>
    </div>
    <div style={{opacity: interpolate(f,[12,38],[0,1],clamp), transform: `translateX(${interpolate(f,[12,60],[55,0],clamp)}px)`}}>
      <Window asset="overview" left={808} top={207} width={1058} height={781} scale={interpolate(f,[0,150],[.988,1.012],clamp)}/>
    </div>
    <div style={{position: 'absolute', left: 703, top: 766, height: 97, width: 272, borderRadius: 14, background: C.green, color: C.paper, boxShadow: '0 12px 35px #173a2b25', padding: '17px 25px', opacity: interpolate(f,[50,68],[0,1],clamp), transform: `translateY(${interpolate(f,[50,78],[16,0],clamp)}px)`}}><div style={{fontSize: 11, letterSpacing: 3, color: '#c6d0b6'}}>A LITTLE CHANGE</div><div style={{fontSize: 21, marginTop: 8, letterSpacing: 2, whiteSpace: 'nowrap'}}>一点小小的调整。</div></div>
  </>;
}

function Feature({chapter}) {
  const f = useCurrentFrame();
  const progress = interpolate(f,[10,42],[0,1],clamp);
  return <>
    <div style={{position: 'absolute', left: 100, top: 273, width: 535, opacity: progress, transform: `translateY(${(1-progress)*18}px)`}}>
      <SmallLabel>{chapter.marker}</SmallLabel>
      <div style={{fontSize: 68, fontWeight: 460, letterSpacing: -1.8, lineHeight: 1.48, marginTop: 31}}>{chapter.title.map(t => <div key={t}>{t}</div>)}</div>
      <div style={{fontSize: 23, color: C.muted, lineHeight: 1.95, marginTop: 31}}>{chapter.description.map(t => <div key={t}>{t}</div>)}</div>
      <div style={{display: 'flex', gap: 10, flexWrap: 'wrap', marginTop: 38}}>{chapter.tags.map((tag,index) => <Tag key={tag} index={index}>{tag}</Tag>)}</div>
      <div style={{marginTop: 64, display: 'flex', gap: 9, alignItems: 'center'}}>{Array.from({length: 5},(_,i) => <div key={i} style={{height: 3, width: i === Number(chapter.id)-2 ? 40 : 15, borderRadius: 2, background: i === Number(chapter.id)-2 ? C.gold : C.line}}/>)}</div>
    </div>
    <div style={{opacity: interpolate(f,[6,27],[0,1],clamp), transform: `translateY(${interpolate(f,[6,42],[24,0],clamp)}px)`}}>
      <Window asset={chapter.asset} left={702} top={193} width={1132} height={794} crop scale={interpolate(f,[0,chapter.duration],[1,1.012],clamp)}/>
    </div>
  </>;
}

function Outro() {
  const f = useCurrentFrame();
  return <>
    <div style={{position: 'absolute', left: 350, top: 215, width: 1220, textAlign: 'center', color: C.paper, opacity: interpolate(f,[8,30],[0,1],clamp), transform: `translateY(${interpolate(f,[8,40],[16,0],clamp)}px)`}}>
      <Mark size={108}/>
      <div style={{fontSize: 66, fontWeight: 450, lineHeight: 1.45, marginTop: 24, letterSpacing: 2}}>留一份备份。<br/>开启新的冒险。</div>
      <div style={{marginTop: 39, fontSize: 22, letterSpacing: 8, color: '#d3ddc2'}}>黎明工坊 <span style={{fontSize: 18, letterSpacing: 3, color: C.gold, marginLeft: 10}}>DAWN ATELIER</span></div>
      <div style={{margin: '36px auto 0', padding: '13px 27px', display: 'inline-flex', border: '1px solid #69816a', borderRadius: 40, fontSize: 18, letterSpacing: 3, color: '#c7d3be'}}>开源 · 本地运行 · 随心调整</div>
    </div>
  </>;
}

function Chapter({chapter}) {
  const f = useCurrentFrame();
  const fade = chapter.from === 0 ? 1 : interpolate(f,[0,15],[0,1],clamp);
  const dark = chapter.type === 'outro';
  return <AbsoluteFill style={{fontFamily: FONT, color: C.ink, opacity: fade}}>
    <Backdrop dark={dark}/>
    <div style={{position: 'absolute', left: 100, top: 62}}><Brand dark={dark}/></div>
    <div style={{position: 'absolute', right: 102, top: 83, fontSize: 13, letterSpacing: 3, color: dark ? '#b2c0a8' : C.muted}}>A LITTLE CORNER OF DAWN</div>
    {chapter.type === 'intro' ? <Intro/> : chapter.type === 'outro' ? <Outro/> : <Feature chapter={chapter}/>}
    <Footer chapter={chapter} dark={dark}/>
  </AbsoluteFill>;
}

export function DawnAtelier() {
  const [fontHandle] = useState(() => delayRender('Load bundled Chinese typeface'));
  useEffect(() => {
    document.fonts.load('500 32px "Dawn Sans"').then(() => continueRender(fontHandle)).catch(cancelRender);
  },[fontHandle]);
  return <AbsoluteFill style={{background: C.paper}}>{CHAPTERS.map(chapter => <Sequence key={chapter.id} from={chapter.from} durationInFrames={chapter.duration}><Chapter chapter={chapter}/></Sequence>)}</AbsoluteFill>;
}
