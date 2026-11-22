import {useId,useState} from 'react';
import type {Locale} from './i18n';
import './styles/home-motion.css';
const copy={
 en:{title:'From an annual plan to public data',steps:['Institution submits the annual plan','Website checks and confirms it','MPALSG monitors submitted plans'],note:'Process illustration, not live statistics. Submission does not require administrator approval.',pause:'Pause animation',play:'Play animation'},
 'sr-Latn':{title:'Od godišnjeg plana do otvorenih podataka',steps:['Institucija podnosi godišnji plan','Sistem proverava i potvrđuje unos','MPALSG prati podnete planove'],note:'Ilustracija postupka, ne podaci uživo. Podnošenje plana ne zahteva odobrenje administratora.',pause:'Pauziraj animaciju',play:'Pokreni animaciju'},
 'sr-Cyrl':{title:'Од годишњег плана до отворених података',steps:['Институција подноси годишњи план','Систем проверава и потврђује унос','MPALSG прати поднете планове'],note:'Илустрација поступка, не подаци уживо. Подношење плана не захтева одобрење администратора.',pause:'Паузирај анимацију',play:'Покрени анимацију'}
};
/** Original MVP v0.3 illustration and animation, retained as a home-only component. */
export default function HomePlanMotion({locale}:{locale:Locale}){
 const [paused,setPaused]=useState(false),id=useId(),t=copy[locale];
 return <section className="annual-plan-motion" data-paused={paused} aria-labelledby={id+'-title'}>
  <div className="motion-heading"><h2 id={id+'-title'}>{t.title}</h2><button className="outline-button motion-control" type="button" onClick={()=>setPaused(v=>!v)}>{paused?t.play:t.pause}</button></div>
  <figure className="motion-card" aria-describedby={id+'-note'}>
<svg className="motion-svg" viewBox="0 0 1200 214" xmlns="http://www.w3.org/2000/svg" role="img" aria-hidden="true">
          <g className="ol" stroke="#1f2a44" strokeWidth="2" strokeLinejoin="round">
            
            <ellipse cx="600" cy="203" rx="585" ry="6" fill="#dfe6f3" stroke="none"/>

            
            <path d="M262 82 C 340 20, 420 30, 470 70" fill="none" stroke="#9fb4e0" strokeWidth="2" strokeDasharray="5 6"/>
            <path d="M730 108 C 790 80, 840 80, 880 92" fill="none" stroke="#9fb4e0" strokeWidth="2" strokeDasharray="5 6"/>

            
            
            <g>
              <path d="M44 150 C 26 132, 22 112, 30 96 C 46 110, 52 130, 48 150 Z" fill="#3f9e5f"/>
              <path d="M50 152 C 58 126, 74 112, 92 110 C 88 132, 72 148, 54 154 Z" fill="#6cc07a"/>
              <path d="M46 152 C 40 132, 44 116, 54 104" fill="none"/>
              <path d="M30 160 L66 160 L60 200 L36 200 Z" fill="#f6c98e"/>
            </g>
            
            <rect x="66" y="92" width="9" height="56" rx="4.5" fill="#c8743c"/>
            <rect x="70" y="140" width="64" height="9" rx="3" fill="#c8743c"/>
            <path d="M78 149 L72 200 M126 149 L132 200" stroke="#8a4a22" strokeWidth="4" fill="none"/>
            
            <rect x="160" y="131" width="6" height="69" fill="#2f4a8a"/>
            <rect x="318" y="131" width="6" height="69" fill="#2f4a8a"/>
            <rect x="148" y="124" width="184" height="8" rx="2" fill="#2f4a8a"/>
            
            <path d="M92 136 H148 A8 8 0 0 1 148 152 H92 Z" fill="#2f4a8a"/>
            <rect x="140" y="148" width="12" height="44" rx="4" fill="#f4c3a1"/>
            <path d="M134 192 H160 A4 4 0 0 1 160 200 H134 Z" fill="#1f2a44"/>
            <path d="M88 142 C 86 114, 96 94, 112 91 L124 93 C 134 98, 137 120, 132 142 Z" fill="#6ab36e"/>
            <rect x="113" y="79" width="8" height="13" fill="#f4c3a1"/>
            <circle cx="120" cy="70" r="13" fill="#f4c3a1"/>
            <path d="M107 72 C 103 54, 126 49, 133 62 C 126 60, 116 63, 113 74 C 112 82, 108 86, 103 83 Z" fill="#1f2a44"/>
            <circle cx="102" cy="62" r="7" fill="#1f2a44"/>
            <g className="m-type">
              <path d="M117 100 L141 116" stroke="#6ab36e" strokeWidth="10" strokeLinecap="round" fill="none"/>
              <path d="M141 116 L176 118" stroke="#f4c3a1" strokeWidth="7" strokeLinecap="round" fill="none"/>
            </g>
            
            <rect x="166" y="118" width="92" height="6" rx="2" fill="#c9d6f0"/>
            <path d="M198 119 L212 72 H270 L256 119 Z" fill="#3d5fa8"/>
            <circle cx="234" cy="96" r="7" fill="none" stroke="#c9d6f0" strokeWidth="2.5"/>
            
            <g className="m-float">
              <rect x="142" y="26" width="104" height="26" rx="7" fill="#2f4a8a"/>
              <path d="M178 52 L186 60 L192 52 Z" fill="#2f4a8a"/>
              <text x="194" y="43.5" textAnchor="middle" className="m-txt" fill="#ffffff" stroke="none">Annual plan 2027</text>
            </g>

            
            <g className="m-doc">
              <rect x="222" y="58" width="40" height="50" rx="4" fill="#ffffff"/>
              <rect x="222" y="58" width="40" height="6" fill="#c6363c" stroke="none"/>
              <rect x="222" y="64" width="40" height="5" fill="#0c4076" stroke="none"/>
              <path d="M229 78 H255 M229 86 H251 M229 94 H255 M229 102 H246" stroke="#9fb4e0" strokeWidth="3" fill="none"/>
            </g>

            
            
            <g className="m-gear">
              <circle cx="438" cy="74" r="17" fill="#f5b84a" stroke="#f5b84a" strokeWidth="9" strokeDasharray="5.5 4.2"/>
              <circle cx="438" cy="74" r="17" fill="#f5b84a"/>
              <circle cx="438" cy="74" r="6" fill="#ffffff"/>
            </g>
            <g className="m-gear rev">
              <circle cx="446" cy="122" r="12" fill="#f08a4b" stroke="#f08a4b" strokeWidth="7" strokeDasharray="4.4 3.6"/>
              <circle cx="446" cy="122" r="12" fill="#f08a4b"/>
              <circle cx="446" cy="122" r="4.5" fill="#ffffff"/>
            </g>
            
            <g className="m-browser">
              <rect x="470" y="20" width="262" height="172" rx="10" fill="#eef3fc"/>
              <path d="M470 46 V30 A10 10 0 0 1 480 20 H722 A10 10 0 0 1 732 30 V46 Z" fill="#3d5fa8"/>
              <circle cx="487" cy="33" r="3.5" fill="#ffffff" stroke="none"/>
              <circle cx="499" cy="33" r="3.5" fill="#ffffff" stroke="none"/>
              <circle cx="511" cy="33" r="3.5" fill="#ffffff" stroke="none"/>
              <rect x="580" y="24" width="42" height="18" rx="4" fill="#2f4a8a" stroke="#ffffff" strokeWidth="1.5"/>
              <text x="601" y="37" textAnchor="middle" className="m-txt" fill="#ffffff" stroke="none">{'{ }'}</text>
              <text x="486" y="66" className="m-txt b" fill="#2f4a8a" stroke="none">Received plans · 2027</text>
            </g>
            
            <g className="m-newrow">
              <rect x="482" y="74" width="238" height="20" rx="5" fill="#fff4e9" stroke="#f08a4b" strokeWidth="1.5"/>
              <rect x="490" y="81" width="120" height="7" rx="3.5" fill="#f08a4b" stroke="none"/>
            </g>
            <g stroke="none">
              <rect x="490" y="105" width="140" height="7" rx="3.5" fill="#9fb4e0"/>
              <rect x="490" y="127" width="110" height="7" rx="3.5" fill="#9fb4e0"/>
              <rect x="490" y="149" width="128" height="7" rx="3.5" fill="#c9d6f0"/>
            </g>
            
            <g className="m-check c1"><circle cx="704" cy="84" r="8" fill="#6ab36e"/><path d="M700 84 l3 3 l5 -6" stroke="#ffffff" strokeWidth="2.4" fill="none" strokeLinecap="round" strokeLinejoin="round"/></g>
            <g className="m-check c2"><circle cx="704" cy="108" r="8" fill="#6ab36e"/><path d="M700 108 l3 3 l5 -6" stroke="#ffffff" strokeWidth="2.4" fill="none" strokeLinecap="round" strokeLinejoin="round"/></g>
            <g className="m-check c3"><circle cx="704" cy="130" r="8" fill="#6ab36e"/><path d="M700 130 l3 3 l5 -6" stroke="#ffffff" strokeWidth="2.4" fill="none" strokeLinecap="round" strokeLinejoin="round"/></g>
            
            <rect className="m-scan" x="478" y="72" width="246" height="3" rx="1.5" fill="#f08a4b" stroke="none"/>
            
            <g className="m-badge">
              <rect x="532" y="164" width="138" height="22" rx="11" fill="#6ab36e"/>
              <text x="601" y="179" textAnchor="middle" className="m-txt b" fill="#ffffff" stroke="none">✓ Submitted · complete</text>
            </g>
            
            <g>
              <path d="M756 160 C 744 140, 744 120, 752 106 C 766 120, 768 142, 762 162 Z" fill="#6cc07a"/>
              <path d="M762 162 C 768 142, 782 130, 798 128 C 794 148, 780 160, 766 164 Z" fill="#3f9e5f"/>
              <path d="M744 168 L 784 168 L 778 200 L 750 200 Z" fill="#f6c98e"/>
            </g>

            
            <circle className="m-pkt p1" cx="742" cy="106" r="5" fill="#3d5fa8"/>
            <circle className="m-pkt p2" cx="742" cy="106" r="5" fill="#f08a4b"/>
            <circle className="m-pkt p3" cx="742" cy="106" r="5" fill="#6ab36e"/>

            
            
            <rect x="880" y="40" width="164" height="98" rx="7" fill="#2f4a8a"/>
            <rect x="887" y="47" width="150" height="82" rx="3" fill="#f4f7fd"/>
            <text x="894" y="61" className="m-txt s b" fill="#2f4a8a" stroke="none">Dashboard</text>
            <g stroke="none">
              <rect className="m-bar b1" x="897" y="96" width="11" height="26" rx="2" fill="#9fb4e0"/>
              <rect className="m-bar b2" x="913" y="86" width="11" height="36" rx="2" fill="#3d5fa8"/>
              <rect className="m-bar b3" x="929" y="92" width="11" height="30" rx="2" fill="#9fb4e0"/>
              <rect className="m-bar b4" x="945" y="76" width="11" height="46" rx="2" fill="#f08a4b"/>
            </g>
            <circle cx="1004" cy="98" r="14" fill="none" stroke="#c9d6f0" strokeWidth="8"/>
            <circle className="m-donut" cx="1004" cy="98" r="14" fill="none" stroke="#3d5fa8" strokeWidth="8" strokeDasharray="62 88" transform="rotate(-90 1004 98)"/>
            <g className="m-toast">
              <rect x="968" y="51" width="64" height="17" rx="4" fill="#6ab36e" stroke="none"/>
              <text x="1000" y="63" textAnchor="middle" className="m-txt s b" fill="#ffffff" stroke="none">+1 plan</text>
            </g>
            <rect x="955" y="138" width="14" height="8" fill="#2f4a8a"/>
            
            <rect x="872" y="155" width="6" height="45" fill="#2f4a8a"/>
            <rect x="1052" y="155" width="6" height="45" fill="#2f4a8a"/>
            <rect x="862" y="146" width="206" height="9" rx="2" fill="#2f4a8a"/>
            <rect x="986" y="141" width="44" height="5" rx="2" fill="#c9d6f0"/>
            
            <rect x="1146" y="100" width="9" height="58" rx="4.5" fill="#c8743c"/>
            <rect x="1088" y="150" width="64" height="9" rx="3" fill="#c8743c"/>
            <path d="M1096 159 L1090 200 M1144 159 L1150 200" stroke="#8a4a22" strokeWidth="4" fill="none"/>
            
            <path d="M1134 146 H1072 A8 8 0 0 0 1072 162 H1134 Z" fill="#1f2a44"/>
            <rect x="1066" y="158" width="12" height="36" rx="4" fill="#f4c3a1"/>
            <path d="M1084 194 H1058 A4 4 0 0 0 1058 202 H1084 Z" fill="#1f2a44"/>
            <path d="M1136 152 C 1138 124, 1128 104, 1112 101 L1100 103 C 1090 108, 1086 130, 1090 152 Z" fill="#f08a4b"/>
            <rect x="1101" y="89" width="8" height="13" fill="#f4c3a1"/>
            <circle cx="1102" cy="80" r="13" fill="#f4c3a1"/>
            <path d="M1090 78 C 1088 64, 1104 60, 1114 66 C 1118 70, 1117 76, 1115 80 C 1110 72, 1100 72, 1094 82 Z" fill="#1f2a44"/>
            <g className="m-nod">
              <path d="M1106 110 L1082 128" stroke="#f08a4b" strokeWidth="10" strokeLinecap="round" fill="none"/>
              <path d="M1082 128 L1030 140" stroke="#f4c3a1" strokeWidth="7" strokeLinecap="round" fill="none"/>
            </g>
            
            <g>
              <rect x="1164" y="36" width="22" height="22" rx="4" fill="#ffffff" stroke="#f08a4b" strokeWidth="2.5"/>
              <rect x="1164" y="66" width="22" height="22" rx="4" fill="#ffffff" stroke="#f08a4b" strokeWidth="2.5"/>
              <rect x="1164" y="96" width="22" height="22" rx="4" fill="#ffffff" stroke="#f08a4b" strokeWidth="2.5"/>
              <path className="m-tick t1" d="M1169 47 l4 4 l8 -9" stroke="#f08a4b" strokeWidth="3" fill="none" strokeLinecap="round" strokeLinejoin="round"/>
              <path className="m-tick t2" d="M1169 77 l4 4 l8 -9" stroke="#f08a4b" strokeWidth="3" fill="none" strokeLinecap="round" strokeLinejoin="round"/>
              <path className="m-tick t3" d="M1169 107 l4 4 l8 -9" stroke="#f08a4b" strokeWidth="3" fill="none" strokeLinecap="round" strokeLinejoin="round"/>
            </g>
          </g>
        </svg>
   <figcaption className="motion-steps">{t.steps.map((step,i)=><span className={'ms s'+(i+1)} key={i}><b aria-hidden="true">{i+1}</b>{step}</span>)}</figcaption>
  </figure>
  <p className="motion-note" id={id+'-note'}>{t.note}</p>
 </section>;
}
