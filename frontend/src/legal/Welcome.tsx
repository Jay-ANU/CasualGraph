import { useState } from 'react';
import { Lock, ShieldCheck, UserCheck } from 'lucide-react';
import { ic } from './icon';
import { ContractSheet } from './art';

export function Welcome({ disabled, onUpload, onDrop }: {
  disabled: boolean; onUpload: () => void; onDrop: (files: FileList) => void;
}) {
  const [dragging, setDragging] = useState(false);
  return <main id="legal-main" tabIndex={-1} className="lv-welcome">
    <div className="lv-welcome-inner">
      <h1>合同风险审查</h1>
      <p className="lv-lede">识别风险条款，提供修改建议与法律依据。</p>
      <section className={`lv-upload ${dragging ? 'is-dragging' : ''}`} aria-label="上传合同"
        onDragOver={e => { e.preventDefault(); if (!disabled && e.dataTransfer.types.includes('Files')) setDragging(true); }}
        onDragLeave={e => { if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setDragging(false); }}
        onDrop={e => { e.preventDefault(); setDragging(false); if (!disabled) onDrop(e.dataTransfer.files); }}>
        <ContractSheet active={dragging} />
        <p className="lv-upload-title">{dragging ? '松开以上传' : '将合同文件拖拽至此处'}</p>
        <button type="button" id="legal-upload-button" className="lv-primary lv-upload-cta" disabled={disabled} onClick={onUpload}>选择文件</button>
        <p className="lv-upload-spec">支持 .docx、.pdf（文本型）、.txt，单个文件不超过 10 MB</p>
      </section>
      <ul className="lv-assurances" aria-label="隐私保护">
        <li><ShieldCheck {...ic} size={15} />敏感信息自动脱敏</li>
        <li><Lock {...ic} size={15} />文件加密存储</li>
        <li><UserCheck {...ic} size={15} />模型分析需授权</li>
      </ul>
    </div>
    <p className="lv-footnote">审查结果仅供参考，不构成法律意见。</p>
  </main>;
}
