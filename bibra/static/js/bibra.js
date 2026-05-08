const mainApp = Vue.createApp({
  data () {
    return {
      extractPending: false,
      fileBlob: null,
      fileName: '',
      fileObjectUrl: null,
      loadingResults: false,
      projects: [],
      results: {},
      selectedProject: '',
      showDraggingEffect: false,
      showErrorMessageExtract: false,
      showErrorMessageFileType: false,
      showErrorMessageURL: false,
      showPreview: false,
      showResults: false,
      url: '',
      version: ''
    }
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
      this.url = ''
      this.fileBlob = null
      URL.revokeObjectURL(this.fileObjectUrl) // Revoke assigned blob URL from uploaded file
      this.fileObjectUrl = null
      this.fileName = ''
      this.results = {}
      this.showPreview = false
      this.showResults = false
      this.loadingResults = false
      this.showErrorMessageFileType = false
      this.showErrorMessageExtract = false
      this.showErrorMessageURL = false
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
      this.showErrorMessageFileType = false
      this.showErrorMessageURL = false
      
      const file = e.dataTransfer.files[0]
      if (file && file.type === 'application/pdf') {
        this.fileBlob = file
        this.fileObjectUrl = URL.createObjectURL(this.fileBlob)
        this.fileName = this.fileBlob.name
        this.showPreview = true
      } else {
        this.showErrorMessageFileType = true
      }
    },
    handleDropzoneClick (e) {
      e.preventDefault()
      this.showErrorMessageFileType = false
      this.showErrorMessageURL = false

      // Click hidden file input to run uploadFile method
      this.$refs.file.click()
    },
    loadFileFromUrl (e) {
      e.preventDefault()
      this.showErrorMessageFileType = false
      this.showErrorMessageURL = false

      // Load file from given URL
      fetch(this.url)
        .then(res => res.blob())
        .then(res => {
          if (res.type === 'application/pdf') {
            // Store the fetched file as a blob and assign a blob URL to it
            this.fileBlob = res
            this.fileObjectUrl = URL.createObjectURL(this.fileBlob)
            this.fileName = this.url.split('/').slice(-1)[0]
            this.showPreview = true
          } else {
            this.showErrorMessageFileType = true
          }
        })
      .catch(err => {
        console.error('Failed to fetch file from URL:', err)
        this.showErrorMessageURL = true
      })
    },
    uploadFile (e) {
      this.showErrorMessageFileType = false
      this.showErrorMessageURL = false

      const file = e.target.files[0]
      if (file && file.type === 'application/pdf') {
        // Store the uploaded file as a blob and assign a blob URL to it
        this.fileBlob = file
        this.fileObjectUrl = URL.createObjectURL(this.fileBlob)
        this.fileName = this.fileBlob.name
        this.showPreview = true
      } else {
        this.showErrorMessageFileType = true
      }
    },
    extract () {
      this.results = {}
      this.showResults = false
      this.loadingResults = true
      this.showErrorMessageExtract = false

      // Only call extract if a previous call is not pending
      if (!this.extractPending) {
        this.extractPending = true

        const formData = new FormData()
        formData.append('files', this.fileBlob)

        fetch(`/v0/projects/${this.selectedProject}/extract`, {
          method: 'POST',
          body: formData
        })
          .then(res => res.json())
          .then(data => {
            this.results = data
            this.loadingResults = false
            this.showResults = true
            this.extractPending = false
          })
        .catch(err => {
          console.error('Failed to extract data from file:', err)

          this.loadingResults = false
          this.extractPending = false
          this.showErrorMessageExtract = true
        })
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
              v-if="showPreview"
              @click="clearInput()"
            >
              Clear input
              <i class="fa-solid fa-xmark" aria-hidden="true"></i>
            </button>
          </div>

          <template v-if="!showPreview">
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
              <form class="input-group" @submit="loadFileFromUrl($event)">
                <input id="url-input" class="form-control" type="url" placeholder="https://example.com/document.pdf" required v-model="url">
                <input id="button-select-url" class="btn btn-primary" type="submit"  value="Fetch PDF">
              </form>
            </div>

            <div class="error-message mb-3 p-2" v-if="showErrorMessageFileType || showErrorMessageURL">
              <span v-if="showErrorMessageFileType">This file format is not supported. Please select a PDF document.</span>
              <span v-else>Failed to fetch file from URL.</span>
            </div>
          </template>
          <template v-else>
            <div id="file-preview" class="mb-3">
              <iframe class="mb-3"
                :src="fileObjectUrl"
                :data-url="fileObjectUrl"
              ></iframe>
              <button class="btn-clear btn btn-secondary"
                :aria-label="'Remove ' + fileName"
                @click="clearInput()"
              >
                <i class="fa-solid fa-file" aria-hidden="true"></i>
                <span>{{ fileName }}</span>
                <i class="fa-solid fa-xmark" aria-hidden="true"></i>
              </button>
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
              :class="{ disabled: !showPreview }"
            >Submit</button>
          </div>
        </div>

        <div id="results" class="col-md-6 ps-4">
          <h2 class="mb-3">Results</h2>
          <template v-if="!showResults">
            <template v-if="!loadingResults">
              <div v-if="showErrorMessageExtract" class="error-message p-2">
                Metadata extraction failed.
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
                        <span class="visually-hidden">Copy</span>
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
