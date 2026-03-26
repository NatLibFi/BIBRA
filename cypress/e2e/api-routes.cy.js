/// <reference types="cypress" />

describe('API Routes', () => {
  describe('GET /v0/', () => {
    it('returns API version information', () => {
      cy.request('/v0/').then((response) => {
        expect(response.status).to.eq(200);
        expect(response.body).to.have.property('version');
        expect(response.body).to.have.property('message');
        expect(response.body.message).to.include('Welcome to BIBRA API');
      });
    });
  });

  describe('GET /v0/projects', () => {
    it('returns a list of projects', () => {
      cy.request('/v0/projects').then((response) => {
        expect(response.status).to.eq(200);
        expect(response.body).to.have.property('projects');
        expect(Array.isArray(response.body.projects)).to.be.true;
        expect(response.body.projects.length).to.be.greaterThan(0);
      });
    });
  });

  describe('POST /v0/projects/{project_id}/extract', () => {
    it('extracts publication metadata from a PDF file', () => {
      const pdfPath = 'test-document.pdf';
      
      cy.fixture(pdfPath, 'binary').then((fileContent) => {
        // Generate a unique boundary
        const boundary = '----CypressFormBoundary' + Date.now().toString(16);
        const crlf = '\r\n';
        
        // Build the multipart body manually
        let body = '';
        
        // Add file part
        body += `--${boundary}${crlf}`;
        body += 'Content-Disposition: form-data; name="files"; filename="test-document.pdf"' + crlf;
        body += 'Content-Type: application/pdf' + crlf + crlf;
        
        // Convert binary string to bytes and then to hex for proper encoding
        let fileHex = '';
        for (let i = 0; i < fileContent.length; i++) {
          const byte = fileContent.charCodeAt(i);
          fileHex += byte.toString(16).padStart(2, '0');
        }
        body += fileHex + crlf;
        
        // Add text part
        body += `--${boundary}${crlf}`;
        body += 'Content-Disposition: form-data; name="text"' + crlf + crlf;
        body += 'Test context for extraction' + crlf;
        
        // Close the boundary
        body += `--${boundary}--${crlf}`;
        
        // Make the request with manually constructed multipart body
        cy.request({
          method: 'POST',
          url: '/v0/projects/project-001/extract',
          headers: {
            'Content-Type': 'multipart/form-data; boundary=' + boundary,
          },
          body: body,
        }).then((response) => {
          expect(response.status).to.eq(200);
          expect(response.body).to.have.property('language');
          expect(response.body).to.have.property('title');
          expect(response.body).to.have.property('creator');
          expect(response.body).to.have.property('year');
          expect(response.body).to.have.property('publisher');
          expect(response.body).to.have.property('doi');
          expect(response.body).to.have.property('e_isbn');
          expect(response.body).to.have.property('type_coar');

          // Verify the expected metadata values from the mock implementation
          expect(response.body.language).to.eq('en');
          expect(response.body.title).to.eq('Machine Learning Approaches for Software Defect Prediction');
          expect(response.body.creator).to.deep.eq(['Smith, John', 'Johnson, Emily']);
          expect(response.body.year).to.eq('2023');
          expect(response.body.publisher).to.deep.eq(['Springer', 'ACM']);
          expect(response.body.doi).to.eq('10.1234/example.doi.12345');
          expect(response.body.e_isbn).to.deep.eq(['978-0-123456-78-9']);
          expect(response.body.type_coar).to.eq('article');
        });
      });
    });
  });
});
