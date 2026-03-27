/// <reference types="cypress" />

describe('Home Page', () => {
  beforeEach(() => {
    cy.visit('/');
  });

  it('displays the BIBRA title', () => {
    cy.get('h1').should('contain', 'BIBRA');
  });

  it('fetches and displays the API version', () => {
    // Wait for the version to be fetched and displayed
    cy.get('#version')
      .should('not.contain', 'Loading...')
      .invoke('text')
      .should('match', /\d+\.\d+\.\d+/);
  });

  it('has a working API documentation link', () => {
    cy.get('.api-link').click();
    cy.url().should('include', '/docs');
  });

  it('shows file preview', () => {
    // Click dropzone and check that it and url input are no longer visible
    cy.get('#dropzone').click()
    cy.get('#dropzone').should('not.exist')
    cy.get('#fetch-from-url').should('not.exist')
    // Check that preview is visible
    cy.get('#file-preview').should('be.visible')
    cy.get('.btn-clear').should('have.length', 2)
  })

  it('shows results after submit', () => {
    // Check that submit button is disabled
    cy.get('.btn-submit').should('have.class', 'disabled')
    // Click dropzone
    cy.get('#dropzone').click()
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
  })

  it('hides preview and results after clear', () => {
    cy.get('#dropzone').click()
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
    cy.get('.btn-clear').should('not.exist', 2)
  })
});
