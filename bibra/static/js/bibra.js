const mainApp = Vue.createApp({
  data () {
    return {
      showPreview: false,
      showResults: false,
      loadingResults: false,
      version: null
    }
  },
  mounted () {
    fetch('/v0/')
      .then(response => response.json())
      .then(data => {
        if (data.version) {
          this.version = data.version
        }
      })
      .catch(err => {
        console.error('Failed to fetch version:', err)
      })
  },
  methods: {
    clearInput () {
      this.showPreview = !this.showPreview
      this.showResults = false
    },
    loadFile () {
      this.showPreview = true
    },
    extract () {
      this.showResults = true
      this.loadingResults = true
      setTimeout(() => {
        this.loadingResults = false
      }, 500)
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
              <i class="fa-solid fa-xmark"></i>
            </button>
          </div>

          <template v-if="!showPreview">
            <div id="dropzone" class="mb-3"
              @click="loadFile()"
            >
              <div id="dropzone-background">
                <i class="fa-solid fa-file-arrow-up"></i>
                <p class="fw-bold mb-0">Drag PDF here</p>
                <p>or click to browse files</p>
              </div>
            </div>

            <div id="fetch-from-url" class="mb-3">
              <label class="input-label" for="url-input">Or fetch from URL</label>
              <div class="input-group">
                <input id="url-input" type="text" class="form-control" placeholder="https://example.com/document.pdf">
                <div class="input-group-append">
                  <button class="btn btn-outline-secondary" type="button">Fetch PDF</button>
                </div>
              </div>
            </div>
          </template>
          <template v-else>
            <div id="file-preview" class="mb-3">
              <iframe src="https://pdfobject.com/pdf/sample.pdf#zoom=70" class="mb-3"></iframe>
              <button class="btn-clear btn btn-secondary"
                @click="clearInput()"
              >
                <i class="fa-solid fa-file"></i>
                <span>sample.pdf</span>
                <i class="fa-solid fa-xmark"></i>
              </button>
            </div>
          </template>

          <label class="input-label" for="select-method">Select extraction method</label>
          <div class="d-flex justify-content-end">
            <select id="select-method" class="form-select me-3 pe-0">
              <option selected="">Method 1</option>
              <option value="1">Method 2</option>
            </select>
            
            <button class="btn-submit btn btn-primary fw-bold"
              @click="extract()"
              :class="{ disabled: !showPreview }"
            >Submit</button>
          </div>
        </div>

        <div id="results" class="col-md-6 ps-4">
          <h2 class="mb-3">Results</h2>
          <p v-if="!showResults">Results will appear here after processing</p>
          <template v-else>
            <i class="fa-solid fa-spinner fa-spin-pulse"
              v-if="loadingResults"
            ></i>
            <table class="table"
              v-else
            >
              <thead>
                <tr>
                  <th scope="col" id="table-col-field">Field</th>
                  <th scope="col">Value</th>
                  <th scope="col" class="table-col-copy">Copy</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>language</td>
                  <td class="table-col-value">en</td>
                  <td class="table-col-copy">
                    <button class="btn-copy btn btn-secondary"><i class="fa-regular fa-copy"></i><span class="visually-hidden">Copy</span></button>
                  </td>
                </tr>
                <tr>
                  <td>title</td>
                  <td class="table-col-value">Machine Learning Approaches for Software Defect Prediction</td>
                  <td class="table-col-copy">
                    <button class="btn-copy btn btn-secondary"><i class="fa-regular fa-copy"></i><span class="visually-hidden">Copy</span></button>
                  </td>
                </tr>
                <tr>
                  <td>creator</td>
                  <td class="table-col-value">Smith, John<br>Johnson, Emily</td>
                  <td class="table-col-copy">
                    <button class="btn-copy btn btn-secondary"><i class="fa-regular fa-copy"></i><span class="visually-hidden">Copy</span></button>
                  </td>
                </tr>
                <tr>
                  <td>year</td>
                  <td class="table-col-value">2023</td>
                  <td class="table-col-copy">
                    <button class="btn-copy btn btn-secondary"><i class="fa-regular fa-copy"></i><span class="visually-hidden">Copy</span></button>
                  </td>
                </tr>
                <tr>
                  <td>publisher</td>
                  <td class="table-col-value">Springer<br>ACM</td>
                  <td class="table-col-copy">
                    <button class="btn-copy btn btn-secondary"><i class="fa-regular fa-copy"></i><span class="visually-hidden">Copy</span></button>
                  </td>
                </tr>
                <tr>
                  <td>doi</td>
                  <td class="table-col-value">10.1234/example.doi.12345</td>
                  <td class="table-col-copy">
                    <button class="btn-copy btn btn-secondary"><i class="fa-regular fa-copy"></i><span class="visually-hidden">Copy</span></button>
                  </td>
                </tr>
                <tr>
                  <td>e_isbn</td>
                  <td class="table-col-value">978-0-123456-78-9</td>
                  <td class="table-col-copy">
                    <button class="btn-copy btn btn-secondary"><i class="fa-regular fa-copy"></i><span class="visually-hidden">Copy</span></button>
                  </td>
                </tr>
                <tr>
                  <td>type_coar</td>
                  <td class="table-col-value">article</td>
                  <td class="table-col-copy">
                    <button class="btn-copy btn btn-secondary"><i class="fa-regular fa-copy"></i><span class="visually-hidden">Copy</span></button>
                  </td>
                </tr>
              </tbody>
            </table>
          </template>
        </div>
      </div>
    </div>

    <div id="version-info" class="container d-flex justify-content-end mb-5">
        <p>Version {{ version ? version : 'Loading...' }}</p>
    </div>
  `
})

mainApp.mount('#main-app')
