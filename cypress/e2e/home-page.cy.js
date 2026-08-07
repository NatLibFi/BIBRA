/// <reference types="cypress" />

describe('Home Page', () => {
    beforeEach(() => {
        cy.visit('/')
    })

    it('displays the BIBRA title', () => {
        cy.get('h1').should('contain', 'BIBRA')
    })

    it('fetches and displays the API version', () => {
        // Wait for the version to be fetched and displayed
        cy.get('#version')
            .should('not.contain', 'Loading...')
            .invoke('text')
            .should('match', /\d+\.\d+\.\d+/)
    })

    it('has a working API documentation link', () => {
        cy.get('.api-link').click()
        cy.url().should('include', '/docs')
    })

    it('fetches projects', () => {
        // Check that correct number of projects is found
        cy.get('#select-method option').should('have.length', 3)
        // Check that correct projects are fetched
        cy.get('#select-method option').eq(0).invoke('text').should('contain', 'GreyLitLM project')
        cy.get('#select-method option').eq(1).invoke('text').should('contain', 'NuExtract project')
        cy.get('#select-method option').eq(2).invoke('text').should('contain', 'Dummy project')
    })

    it('shows file preview', () => {
        // Upload pdf file and check that dropzone and url input are no longer visible
        cy.get('input[type=file]').selectFile('cypress/fixtures/test-document.pdf', { force: true })
        cy.get('#dropzone').should('not.exist')
        cy.get('#fetch-from-url').should('not.exist')
        // Check that preview is visible
        cy.get('#file-preview').should('be.visible')
        cy.get('.btn-clear').should('have.length', 2)
    })

    it('uploads files with drag and drop', () => {
        // Check that file preview is not visible
        cy.get('#file-preview').should('not.exist')
        // Drop file on dropzone
        cy.get('#dropzone').selectFile('cypress/fixtures/test-document.pdf', { action: 'drag-drop' })
        // Check that preview is visible
        cy.get('#file-preview').should('be.visible')
    })

    it('fetches files from URL', () => {
        // Check that file preview is not visible
        cy.get('#file-preview').should('not.exist')
        // Type in pdf url
        cy.get('#url-input').type('https://pdfobject.com/pdf/sample.pdf')
        // Click button to fetch pdf
        cy.get('#button-select-url').click()
        // Check that preview is visible
        cy.get('#file-preview').should('be.visible')
    })

    it('shows results after submit', () => {
        // Check that submit button is disabled
        cy.get('.btn-submit').should('have.class', 'disabled')
        // Select Dummy project
        cy.get('select').select('Dummy project')
        // Upload pdf file
        cy.get('input[type=file]').selectFile('cypress/fixtures/test-document.pdf', { force: true })
        // Check that results are not shown
        cy.get('#results p').should('be.visible')
        cy.get('#results table').should('not.exist')
        // Check that submit button is not disabled
        cy.get('.btn-submit').should('not.have.class', 'disabled')
        // Click submit button
        cy.get('.btn-submit').click()
        // Check that results are visible
        cy.get('#results p').should('not.exist')
        cy.get('#results table').should('be.visible')
        // Check that copy buttons copy correct values
        cy.get('.btn-copy').eq(0).click()
        cy.window().its('navigator.clipboard').invoke('readText').then((result) => { }).should('equal', 'en');
    })

    it('hides preview and results after clear', () => {
        // Select Dummy project
        cy.get('select').select('Dummy project')
        // Upload pdf file and submit
        cy.get('input[type=file]').selectFile('cypress/fixtures/test-document.pdf', { force: true })
        cy.get('.btn-submit').click()
        // Check that results are visible
        cy.get('#results p').should('not.exist')
        cy.get('#results table').should('be.visible')
        // Click clear button
        cy.get('.btn-clear').eq(0).click()
        // Check that results are not visible
        cy.get('#results p').should('be.visible')
        cy.get('#results table').should('not.exist')
        // Check that dropzone and preview is not
        cy.get('#dropzone').should('be.visible')
        cy.get('#fetch-from-url').should('be.visible')
        cy.get('#file-preview').should('not.exist')
        cy.get('.btn-clear').should('not.exist')
    })

    it('shows correct error messages', () => {
        // Upload non-pdf file
        cy.get('input[type=file]').selectFile('cypress/fixtures/test-document.txt', { force: true })
        // Check that file preview does not exist
        cy.get('#file-preview').should('not.exist')
        // Check that correct error message is displayed
        cy.get('.error-message').should('have.length', 1)
        cy.get('.error-message').eq(0).invoke('text').should('contain', 'This file format is not supported. Please select a PDF document.')
        // Input faulty URL
        cy.get('#url-input').type('https://example.com/')
        cy.get('#button-select-url').click()
        // Check that correct error message is displayed
        cy.get('.error-message').should('have.length', 1)
        cy.get('.error-message').eq(0).invoke('text').should('contain', 'Failed to fetch file from URL.')

        // Intercept and block all POST requests
        cy.intercept({
            method: 'POST',
            url: '*'
        }, req => {
            req.destroy()
        })
        // Upload PDF file and submit it
        cy.get('input[type=file]').selectFile('cypress/fixtures/test-document.pdf', { force: true })
        cy.get('.btn-submit').click()
        // Check that correct error message is displayed
        cy.get('.error-message').should('have.length', 1)
        cy.get('.error-message').eq(0).invoke('text').should('contain', 'Metadata extraction failed.')
    })
})
