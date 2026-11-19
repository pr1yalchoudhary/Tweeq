import Icon from './Icon'
import UploadIllustration from './UploadIllustration'

export default function UploadScreen({ file, dragging, locked, consent, busy, progress, onChoose, onDrag, onConsent, onUpload, consentText }) {
  return <section className="upload-screen" aria-label="Upload recording">
    <div className="upload-panel-heading"><span>Upload</span></div>
    <div className="upload-card">
      <div className={`drop-zone ${dragging ? 'dragging' : ''}`} onDragOver={event => { event.preventDefault(); onDrag(true) }} onDragLeave={() => onDrag(false)} onDrop={event => { event.preventDefault(); onDrag(false); if (!locked) onChoose(event.dataTransfer.files[0]) }}>
        <div className="upload-icon"><UploadIllustration/></div>
        <h1>Upload your recording</h1>
        <p>Choose an audio file to get started.</p>
        <small>or drag and drop · MP3 or WAV · Up to 25 MB</small>
        <label className={`button primary upload-choice ${locked ? 'disabled' : ''}`}><Icon name="upload" size={24}/>Choose File<input id="recording-file" aria-label="Choose File" disabled={locked} type="file" accept=".mp3,.wav,audio/mpeg,audio/wav" onChange={event => onChoose(event.target.files[0])}/></label>
      </div>
      <div className="upload-details">
        <h2>Your recording</h2>
        {file ? <div className="selected-file"><Icon name="waveform" size={28}/><span><strong>{file.name}</strong><small>{(file.size / 1024 / 1024).toFixed(2)} MB · Ready to open</small></span></div>
          : <div className="file-empty"><Icon name="folder" size={28}/><p>No file selected</p></div>}
        <label className="consent"><input type="checkbox" checked={consent} disabled={locked} onChange={event => onConsent(event.target.checked)}/><span>{consentText}</span></label>
        <button className="primary wide open-recording" disabled={locked || !file || !consent} onClick={onUpload}>{busy === 'upload' ? progress < 100 ? `Uploading… ${progress}%` : 'Preparing your recording…' : 'Open recording'}<Icon name="arrow" size={24}/></button>
        {busy === 'upload' && <progress value={progress} max="100" aria-label="Upload progress"/>}
        <p className="privacy-note">Authorized voice samples and text are sent to Fish Audio when you use AI editing. Requests may consume credits.</p>
        <p className="original-note"><Icon name="shield" size={20}/>Your original recording stays untouched.</p>
      </div>
    </div>
  </section>
}
