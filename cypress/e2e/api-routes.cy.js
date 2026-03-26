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
});
