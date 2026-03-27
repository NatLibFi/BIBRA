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
});
