const mainApp = Vue.createApp({
  data () {
    return {
      extractPending: false,
      errorMessageExtract: '',
      loadingResults: false,
      projects: [],
      results: {},
      selectedProject: '',
      showDraggingEffect: false,
      showErrorMessageFileType: false,
      showResults: false,
      source: null, // null | { type: 'file', blob, objectUrl, name } | { type: 'url', url }
      url: '',
      version: ''
    }
  },
  computed: {
    isUrlSource () { return this.source?.type === 'url' },
    isFileSource () { return this.source?.type === 'file' }
  },
  mounted () {
    // Fetch BIBRA version information
    fetch('/v0/')
      .then(res => res.json())
      .then(data => {
        if (data.version) {
          this.version = data.version
        }
      })
      .catch(err => {
        console.error('Failed to fetch version:', err)
      })

    // Fetch projects
    fetch('/v0/projects')
      .then(res => res.json())
      .then(data => {
        if (data.projects) {
          this.projects = data.projects
          this.selectedProject = this.projects[0] && this.projects[0].id
        }
      })
      .catch(err => {
        console.error('Failed to fetch projects:', err)
        // Should an error message be shown in UI?
      })
  },
  methods: {
    clearInput () {
      // Reset input data
      if (this.isFileSource) URL.revokeObjectURL(this.source.objectUrl)
      this.extractPending = false
      this.errorMessageExtract = ''
      this.loadingResults = false
      this.results = {}
      this.showResults = false
      this.showErrorMessageFileType = false
      this.source = null
      this.url = ''
    },
    copy (value) {
      if (Array.isArray(value)) {
        navigator.clipboard.writeText(value.join('\n'))
          .catch(err => {
            console.error(err)
          })
      } else {
        navigator.clipboard.writeText(value)
          .catch(err => {
            console.error(err)
          })
      }
    },
    dragOver(e) {
      e.stopPropagation()
      e.preventDefault()
      this.showDraggingEffect = true
    },
    dragLeave(e) {
      e.stopPropagation()
      e.preventDefault()
      this.showDraggingEffect = false
    },
    drop (e) {
      e.stopPropagation()
      e.preventDefault()
      this.showDraggingEffect = false
      
      this.setFile(e.dataTransfer.files[0])
    },
    handleDropzoneClick (e) {
      e.preventDefault()
      // Click hidden file input to run uploadFile method
      this.$refs.file.click()
    },
    uploadFile (e) {
      this.setFile(e.target.files[0])
    },
    setFile (file) {
      this.showErrorMessageFileType = false

      if (!file || file.type !== 'application/pdf') {
        this.showErrorMessageFileType = true
        return
      }
      if (this.isFileSource) {
        URL.revokeObjectURL(this.source.objectUrl)
      }
      // Store the uploaded file as a blob and assign a blob URL to it
      this.source = {
        type: 'file',
        blob: file,
        objectUrl: URL.createObjectURL(file),
        name: file.name
      }
    },
    setUrl (e) {
      e.preventDefault()
      this.showErrorMessageFileType = false

      this.source = { type: 'url', url: this.url }
    },
    async extract () {
      if (this.extractPending) return // Only call extract if a previous call is not pending

      this.extractPending = true
      this.errorMessageExtract = ''
      this.loadingResults = true
      this.results = {}
      this.showResults = false

      const formData = new FormData()
      if (this.isUrlSource) {
        formData.append('url', this.source.url)
      } else {
        formData.append('files', this.source.blob)
      }
      const endpoint = this.isUrlSource ? 'extract-url' : 'extract'

      try {
        const res = await fetch(`/v0/projects/${this.selectedProject}/${endpoint}`, { method: 'POST', body: formData })
        const data = await res.json()

        if (!res.ok) {
          console.error('Failed to extract data:', data.detail)
          // Only show error if request wasn't cancelled by user
          if (this.extractPending) {
            this.results = {}
            this.showResults = false
            this.errorMessageExtract = data.detail
          }
          return
        }

        if (this.extractPending) {
          this.results = data
          this.showResults = true
        }
      } catch (err) {
        console.error('Failed to extract data:', err)
        // Only show error if request wasn't cancelled by user
        if (this.extractPending) {
          this.results = {}
          this.showResults = false
          this.errorMessageExtract = 'Metadata extraction failed.'
        }
      } finally {
        this.loadingResults = false
        this.extractPending = false
      }
    }
  },
  template: `
    <div id="content" class="container p-4">
      <div class="row">
        <div id="input" class="col-md-6 pe-4">
          <div class="d-flex mb-3">
            <h2 class="my-auto">Input</h2>
            <button class="btn-clear ms-auto btn btn-primary"
              v-if="source"
              @click="clearInput()"
            >
              Clear input
              <i class="fa-solid fa-xmark" aria-hidden="true"></i>
            </button>
          </div>

          <template v-if="!source">
            <div id="dropzone" class="mb-3" role="button" tabindex="0"
              :class="{ 'dragging': showDraggingEffect }"
              @click="handleDropzoneClick($event)"
              @keydown.space="handleDropzoneClick($event)"
              @keydown.enter="handleDropzoneClick($event)"
              @drop="drop($event)"
              @dragover="dragOver($event)"
              @dragleave="dragLeave($event)"
            >
              <div id="dropzone-background">
                <i class="fa-solid fa-file-arrow-up" aria-hidden="true"></i>
                <p class="fw-bold mb-0">Drag PDF here</p>
                <p class="mb-0">or click to browse files</p>
              </div>
            </div>
            <input class="d-none" type="file" accept="application/pdf" ref="file" @change="uploadFile($event)">

            <div id="fetch-from-url" class="mb-3">
              <label class="input-label" for="url-input">Or fetch from URL</label>
              <form class="input-group" @submit="setUrl($event)">
                <input id="url-input" class="form-control" type="url" placeholder="https://example.com/document.pdf" required v-model="url">
                <input id="button-select-url" class="btn btn-primary" type="submit"  value="Select URL">
              </form>
            </div>

            <div class="error-message mb-3 p-2" role="alert" v-if="showErrorMessageFileType">
              <span>This file format is not supported. Please select a PDF document.</span>
            </div>
          </template>
          <template v-else>
            <div class="mb-3">
              <div v-if="isUrlSource" id="url-preview" class="p-3">
                <p class="mb-2">
                  Using document: <a :href="url" title="Open document in a new tab" target="_blank">
                    {{ url }}<i class="fa-solid fa-arrow-up-right-from-square"></i>
                  </a>
                </p>
                <p class="mb-0">
                  The file is downloaded and validated on the server after submission.
                </p>
              </div>
              <div v-else id="file-preview">
                <iframe class="mb-3"
                  :title="source.name"
                  :src="source.objectUrl"
                ></iframe>
                <button class="btn-clear btn btn-secondary"
                  :aria-label="'Remove ' + source.name"
                  @click="clearInput()"
                >
                  <i class="fa-solid fa-file me-1" aria-hidden="true"></i>
                  <span>{{ source.name }}</span>
                  <i class="fa-solid fa-xmark" aria-hidden="true"></i>
                </button>
              </div>
            </div>
          </template>

          <label class="input-label" for="select-method">Select extraction method</label>
          <div class="d-flex justify-content-end">
            <select id="select-method" class="form-select me-3 pe-0" v-model="selectedProject">
              <option 
                v-for="p in projects"
                :key="p.id"
                :value="p.id"
              >{{ p.name }}</option>
            </select>
            
            <button class="btn-submit btn btn-primary fw-bold"
              @click="extract()"
              :class="{ disabled: !source || loadingResults }"
              :disabled="!source || loadingResults"
            >Submit</button>
          </div>
        </div>

        <div id="results" class="col-md-6 ps-4">
          <h2 class="mb-3">Results</h2>
          <template v-if="!showResults">
            <template v-if="!loadingResults">
              <div v-if="errorMessageExtract" class="error-message p-2" role="alert">
                {{ errorMessageExtract }}
              </div>
              <p v-else>Results will appear here after processing</p>
            </template>
            <template v-else>
              <i class="fa-solid fa-spinner fa-spin-pulse" aria-hidden="true"></i>
              <span class="visually-hidden">Loading results</span>
            </template>
          </template>
          <template v-else>
            <table class="table">
              <thead>
                <tr>
                  <th scope="col" id="table-col-field">Field</th>
                  <th scope="col">Value</th>
                  <th scope="col" class="table-col-copy">Copy</th>
                </tr>
              </thead>
              <tbody>
                <template v-for="(value, key) in results" :key="key">
                  <tr v-if="value && value.length > 0">
                    <td>{{ key }}</td>
                    <td class="table-col-value">
                      <template v-if="Array.isArray(value)">
                        <span v-for="(x, i) in value" :key="i">
                          {{ x }}<br v-if="i < value.length - 1">
                        </span>
                      </template>
                      <template v-else>
                        {{ value }}
                      </template>
                    </td>
                    <td class="table-col-copy">
                      <button class="btn-copy btn btn-secondary" @click="copy(value)">
                        <i class="fa-regular fa-copy" aria-hidden="true"></i>
                        <span class="visually-hidden">Copy {{ key }}</span>
                      </button>
                    </td>
                  </tr>
                </template>
              </tbody>
            </table>
          </template>
        </div>
      </div>
    </div>

    <div id="version-info" class="container d-flex justify-content-end mb-5 p-0">
        <p>Version <span id="version">{{ version ? version : 'Loading...' }}</span></p>
    </div>
  `
})

mainApp.mount('#main-app')
