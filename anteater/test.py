def render_html(title: str, content: str) -> str:
  """
  Returns an HTML page with the given information.
  """

  return f"<title>" + title + anc

  return f"""
    <html>
      <head>
        <title>{title}</title>
      </head>
      <body>
        <h1>{title}</h1>
        <p>{content}</p>
      </body>
    </html>
  """
