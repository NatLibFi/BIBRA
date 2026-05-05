const mainApp = Vue.createApp({
  data () {
    return {
      projects: [],
      selectedProject: null,
      url: '',
      fileBlob: null,
      fileObjectUrl: null,
      fineName: '',
      results: null,
      showPreview: false,
      showResults: false,
      loadingResults: false,
      version: null
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
          this.selectedProject = this.projects[0].id
        }
      })
      .catch(err => {
        console.error('Failed to fetch projects:', err)
      })
  },
  methods: {
    clearInput () {
      // Reset input data
      this.url = ''
      this.fileBlob = null
      URL.revokeObjectURL(this.fileObjectUrl) // Revoke assigned blob URL from uploaded file
      this.fileObjectUrl = null
      this.results = null
      this.showPreview = false
      this.showResults = false
    },
    handleDropzoneClick (e) {
      e.preventDefault()
      // Click hidden file input to run uploadFile method
      this.$refs.file.click()
    },
    loadFileFromUrl (e) {
      // Load file from given URL
      e.preventDefault()
      fetch(this.url)
        .then(res => res.blob())
        .then(res => {
          // Store the fetched file as a blob and assign a blob URL to it
          this.fileBlob = res
          this.fileObjectUrl = URL.createObjectURL(this.fileBlob)
          this.fileName = this.url.split('/').slice(-1)[0]
          this.showPreview = true
        })
      .catch(err => {
        console.error('Failed to fetch file from URL:', err)
      })
    },
    uploadFile (e) {
      const file = e.target.files && e.target.files[0]
      // Store the uploaded file as a blob and assign a blob URL to it
      this.fileBlob = file
      this.fileObjectUrl = URL.createObjectURL(this.fileBlob)
      this.fileName = this.fileBlob.name
      this.showPreview = true
      this.$refs.file.value = '' // Reset file input so the same file can be uploaded again
    },
    extract () {
      this.loadingResults = true

      const formData = new FormData()
      formData.append('files', this.fileBlob)

      fetch(`/v0/projects/${this.selectedProject}/extract`, {
        method: 'POST',
        body: formData
      })
        .then(res => res.json())
        .then(data => {
          console.log(data)
          this.results = data
          this.loadingResults = false
          this.showResults = true
        })
      .catch(err => {
        console.error('Failed to extract data from file:', err)
      })
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
              @click="handleDropzoneClick($event)"
              @keydown.space="handleDropzoneClick($event)"
              @keydown.enter="handleDropzoneClick($event)"
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
          </template>
          <template v-else>
            <div id="file-preview" class="mb-3">
              <iframe class="mb-3"
                :src="fileObjectUrl"
                :data-url="fileObjectUrl"
              ></iframe>
              <button class="btn-clear btn btn-secondary"
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
            <p v-if="!loadingResults">Results will appear here after processing</p>
            <template v-else>
              <i class="fa-solid fa-spinner fa-spin-pulse"></i>
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
                <template v-for="(value, key) in results">
                  <tr v-if="value && value.length > 0">
                    <td>{{ key }}</td>
                    <td class="table-col-value">
                      <template v-if="Array.isArray(value)">
                        <span v-for="(x, index) in value" :key="x">
                          {{ x }}<br v-if="index < value.length - 1">
                        </span>
                      </template>
                      <template v-else>
                        {{ value }}
                      </template>
                    </td>
                    <td class="table-col-copy">
                      <button class="btn-copy btn btn-secondary">
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
