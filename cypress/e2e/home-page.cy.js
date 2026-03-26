/// <reference types="cypress" />

describe('Home Page', () => {
  beforeEach(() => {
    cy.visit('/');
  });

  it('displays the BIBRA API title', () => {
    cy.get('h1').should('contain', 'BIBRA API');
  });

  it('displays a version loading message', () => {
    cy.get('#version').should('contain', 'Loading...');
  });

  it('fetches and displays the API version', () => {
    // Wait for the version to be fetched
    cy.get('#version', { timeout: 10000 })
      .should('not.contain', 'Loading...')
      .and('match', /\d+\.\d+\.\d+/);
  });

  it('has a link to API documentation', () => {
    cy.get('.api-link')
      .should('exist')
      .and('have.attr', 'href', '/v0');
  });

  it('has a working API documentation link', () => {
    cy.get('.api-link').click();
    cy.url().should('include', '/v0');
    cy.get('h1').should('contain', 'BIBRA API');
  });
});
