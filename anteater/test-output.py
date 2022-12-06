
def render_html(title: str, content: str) -> str:
  """
  Returns an HTML page with the given information.
  """
  return f"""
  <html>
    <head>
      <title>{escape(title)}</title>
    </head>
    <body>
      <h1>{escape(title)}</h1>
      <p>{escape(content)}</p>
    </body>
  </html>
  """

